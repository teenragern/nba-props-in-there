import time
from datetime import datetime
import dateutil.parser
from dateutil import tz
from typing import List, Dict, Any, Tuple
from src.utils.logging_utils import get_logger
from src.data.db import DatabaseClient
from src.clients.odds_api import OddsApiClient
from src.clients.nba_stats import NbaStatsClient
from src.clients.telegram_bot import TelegramBotClient
from src.config import PROP_MARKETS, EDGE_MIN
from src.models.projections import build_player_projection
from src.models.distributions import get_probability_distribution
from src.models.devig import decimal_to_implied_prob, devig_two_way
from src.models.edge_ranker import rank_edges
from src.pipelines.send_alerts import evaluate_and_alert

logger = get_logger(__name__)
_PROJECTIONS_CACHE = {}

def get_best_odds(bookmakers: List[Dict], player_name: str, market_key: str, line: float) -> Tuple[Dict, Dict]:
    best_over = {"price": 0.0, "book": None}
    best_under = {"price": 0.0, "book": None}
    
    for book in bookmakers:
        for mkt in book.get('markets', []):
            if mkt['key'] != market_key: continue
            for outcome in mkt.get('outcomes', []):
                if outcome.get('description') != player_name or outcome.get('point') != line: continue
                side = outcome.get('name', '').lower()
                price = outcome.get('price', 0.0)
                if side == 'over' and price > best_over['price']:
                    best_over = {"price": price, "book": book['title']}
                elif side == 'under' and price > best_under['price']:
                    best_under = {"price": price, "book": book['title']}
    return best_over, best_under

def scan_props():
    logger.info("Initializing Phase 3 scan pipeline...")
    db = DatabaseClient()
    odds_client = OddsApiClient()
    stats_client = NbaStatsClient()
    bot = TelegramBotClient()
    
    today = datetime.now().strftime('%Y-%m-%d')
    local_zone = tz.tzlocal()
    
    try:
        events = odds_client.get_events()
        today_events = []
        for e in events:
            dt = dateutil.parser.isoparse(e['commence_time'])
            if dt.astimezone(local_zone).strftime('%Y-%m-%d') == today:
                today_events.append(e)
    except Exception as e:
        logger.error(f"Failed to fetch events: {e}")
        return
        
    candidates = []

    for event in today_events:
        event_id = event['id']
        home = event['home_team']
        away = event['away_team']
        
        try: odds_data = odds_client.get_event_odds(event_id=event_id, markets=PROP_MARKETS)
        except: continue
            
        bookmakers = odds_data.get('bookmakers', [])
        if not bookmakers: continue
            
        players_in_event = set()
        prices_by_market = {}
        
        for mkt in PROP_MARKETS:
            prices_by_market[mkt] = {}
            line_records = []
            for book in bookmakers:
                for book_mkt in book.get('markets', []):
                    if book_mkt['key'] == mkt:
                        for outcome in book_mkt.get('outcomes', []):
                            player = outcome.get('description')
                            line = outcome.get('point')
                            if not player or not line: continue
                            players_in_event.add(player)
                            if player not in prices_by_market[mkt]: prices_by_market[mkt][player] = set()
                            prices_by_market[mkt][player].add(line)
                            
                            # Phase 5 Line history prep
                            side = outcome.get('name', '').upper()
                            price = outcome.get('price', 0.0)
                            if price > 0:
                                raw_ip = 1.0 / price
                                line_records.append((player, mkt, book.get('title'), line, side, price, raw_ip))
                                
            if line_records:
                db.insert_line_history_batch(line_records)
        
        # Phase 3 Lineup-Aware Usage Redistribution
        # 1. Identify OUT players for the teams involved
        out_players = []
        with db.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT player_name, team FROM injury_reports WHERE game_date = ? AND status = 'Out' AND (team = ? OR team = ?)", (today, home, away))
            for row in cursor.fetchall():
                out_players.append(row['player_name'])
                
        # Calculate Usage shifts logic 
        # (Simplified: flat 0.15 bump to starters if any major out_player exists)
        # In a generic system we'd parse precise usage, but we're mimicking a V1 logic
        usage_bump = 0.0 
        if out_players:
            usage_bump = 0.15 # Give active players a 15% bump
            logger.info(f"{away} @ {home} has OUT players {out_players}. Applying +15% usage boost to active rosters.")

        # Phase 3 Opponent Splitting Context
        with db.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM team_context_daily WHERE game_date = ? AND team_id IN (SELECT team_id FROM teams WHERE team_name = ? OR team_name = ?)", (today, home, away))
            team_stats = {row['team_id']: dict(row) for row in cursor.fetchall()}
            
        # Mocking finding team context
        opponent_multiplier = 1.0 # Default fallback
        # In full production we link home->away context, etc.

        for player_name in players_in_event:
            injury_status = "Healthy"
            if player_name in out_players:
                injury_status = "Out"
            else:
                with db.get_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT status FROM injury_reports WHERE player_name = ? AND game_date = ?", (player_name, today))
                    inj_row = cursor.fetchone()
                    if inj_row: injury_status = inj_row['status']
                    
            if "out" in injury_status.lower():
                continue # Skip OUT players

            cache_key = f"{player_name}_{today}"
            if cache_key not in _PROJECTIONS_CACHE:
                try:
                    from nba_api.stats.static import players
                    found = players.find_players_by_full_name(player_name)
                    if not found: continue
                    player_id = found[0]['id']
                    logs = stats_client.get_player_game_logs(player_id)
                    time.sleep(0.6)
                    _PROJECTIONS_CACHE[cache_key] = {"logs": logs, "pid": player_id}
                except: continue
                    
            p_data = _PROJECTIONS_CACHE[cache_key]
            logs = p_data["logs"]
            
            for mkt in PROP_MARKETS:
                if player_name not in prices_by_market[mkt]: continue
                for line in prices_by_market[mkt][player_name]:
                    
                    proj = build_player_projection(
                        player_id=player_name,
                        market=mkt, line=line,
                        recent_logs=logs, season_logs=logs,
                        injury_status=injury_status,
                        team_pace=99.0, opp_pace=99.0,
                        opponent_multiplier=opponent_multiplier,
                        usage_shift=usage_bump
                    )
                    
                    if not proj or proj.get('mean', 0) == 0: continue
                    dists = get_probability_distribution(mkt, proj['mean'], line, logs=logs, variance_scale=proj.get('variance_scale', 1.0))
                    best_over, best_under = get_best_odds(bookmakers, player_name, mkt, line)
                    
                    if best_over['price'] > 0 and best_under['price'] > 0:
                        raw_imp_o = decimal_to_implied_prob(best_over['price'])
                        raw_imp_u = decimal_to_implied_prob(best_under['price'])
                        imp_over, imp_under = devig_two_way(raw_imp_o, raw_imp_u)
                    else:
                        imp_over = decimal_to_implied_prob(best_over['price'])
                        imp_under = decimal_to_implied_prob(best_under['price'])
                        
                    if best_over['price'] > 0:
                        over_metrics = db.get_market_metrics(player_name, mkt, line, "OVER")
                        candidates.append({**proj, "side": "OVER", "book": best_over['book'], "book_role": db.get_bookmaker_role(best_over['book']), "odds": best_over['price'], "model_prob": dists['prob_over'], "implied_prob": imp_over, "home_team": home, "away_team": away, "steam_flag": over_metrics['steam_flag'], "velocity": over_metrics['velocity'], "dispersion": over_metrics['dispersion']})
                    if best_under['price'] > 0:
                        under_metrics = db.get_market_metrics(player_name, mkt, line, "UNDER")
                        candidates.append({**proj, "side": "UNDER", "book": best_under['book'], "book_role": db.get_bookmaker_role(best_under['book']), "odds": best_under['price'], "model_prob": dists['prob_under'], "implied_prob": imp_under, "home_team": home, "away_team": away, "steam_flag": under_metrics['steam_flag'], "velocity": under_metrics['velocity'], "dispersion": under_metrics['dispersion']})
                        
    ranked_edges = rank_edges(candidates)
    actionable = [e for e in ranked_edges if e.get('edge', 0) >= EDGE_MIN]
    
    for edge in actionable:
        print(f"EDGE FOUND: {edge['player_id']} {edge['market']} {edge['side']} {edge['line']} @ {edge['book']} ({edge['odds']}) [Role: {edge.get('book_role', 'rec')}]")
        evaluate_and_alert(edge, db, bot)

if __name__ == "__main__":
    scan_props()
