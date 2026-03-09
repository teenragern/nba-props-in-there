from typing import Dict, Any
from src.utils.logging_utils import get_logger
from src.clients.telegram_bot import TelegramBotClient
from src.data.db import DatabaseClient
from src.config import BANKROLL, KELLY_FRACTION

logger = get_logger(__name__)

def evaluate_and_alert(edge_data: Dict[str, Any], db: DatabaseClient, bot: TelegramBotClient):
    player = edge_data.get('player_id', 'Unknown')
    market = edge_data.get('market', 'Unknown')
    line = edge_data.get('line', 0.0)
    side = edge_data.get('side', 'Unknown')
    book = edge_data.get('book', 'Unknown')
    edge = edge_data.get('edge', 0.0)
    odds = edge_data.get('odds', 0.0)
    
    if db.check_recent_alert(player, market, line, side, edge):
        logger.info(f"Skipping duplicate alert (or no edge improvement) for {player} {market} {side} {line}")
        return

    home = edge_data.get('home_team', 'Home')
    away = edge_data.get('away_team', 'Away')
    
    # Fractional Kelly Stake Sizing
    stake = 0.0
    if odds > 1:
        stake = BANKROLL * (edge / (odds - 1.0)) * KELLY_FRACTION
        if stake > BANKROLL * 0.05:
            stake = BANKROLL * 0.05
            
    # Phase 5: Portfolio Exposure Control
    MAX_DAILY_RISK = BANKROLL * 0.25 # 25% of bankroll per day limit
    MAX_PER_GAME = BANKROLL * 0.10
    
    with db.get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(stake) as total_risk FROM alerts_sent WHERE date(timestamp) = date('now')")
        row = cursor.fetchone()
        current_daily_risk = row['total_risk'] if row and row['total_risk'] else 0.0
        
        # In a generic setup, we'd also track game_id directly in alerts_sent, but we'll approximate with daily risk
        if current_daily_risk + stake > MAX_DAILY_RISK:
            logger.warning(f"Skipping alert for {player} - Daily risk limit reached ({current_daily_risk:.2f}/{MAX_DAILY_RISK:.2f})")
            return
            
    db.insert_alert(
        player_name=player,
        market=market,
        line=line,
        side=side,
        edge=edge,
        book=book,
        odds=odds,
        stake=stake
    )
    
    # Fractional Kelly and Exposure limits already handled above.

    msg = f"<b>🔥 NBA PROP EDGE</b>\n\n" \
          f"Game: {away} @ {home}\n" \
          f"Player: {player}\n" \
          f"Market: {market}\n" \
          f"Side: {side}\n" \
          f"Line: {line}\n" \
          f"Best Book: {book}\n" \
          f"Odds: { odds }\n\n" \
          f"Model Prob: {edge_data.get('model_prob', 0.0):.3f}\n" \
          f"Implied Prob: {edge_data.get('implied_prob', 0.0):.3f}\n" \
          f"Edge: {edge:.3%}\n" \
          f"EV: {edge_data.get('ev', 0.0):.3%}\n\n" \
          f"Projected Mean: {edge_data.get('mean', 0.0):.2f}\n" \
          f"Proj Minutes: {edge_data.get('projected_minutes', 0.0):.1f}\n" \
          f"Injury: {edge_data.get('injury_status', 'Healthy')}\n" \
          f"Usage Boost: {edge_data.get('usage_boost', 0.0):.1%}\n" \
          f"Feedback Factor: {edge_data.get('feedback_factor_applied', 1.0):.2f}\n\n" \
          f"<b>Suggested Stake (Kelly):</b> ${stake:.2f}"
          
    bot.send_message(msg)
    logger.info(f"Alert sent for {player} {market} {side} {line}")
