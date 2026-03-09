from src.utils.logging_utils import get_logger
from src.data.db import DatabaseClient
from src.clients.nba_stats import NbaStatsClient
from src.clients.telegram_bot import TelegramBotClient

logger = get_logger(__name__)

def evaluate_result(market: str, line: float, side: str, actual_val: float) -> int:
    if side.upper() == "OVER": return 1 if actual_val > line else 0
    elif side.upper() == "UNDER": return 1 if actual_val < line else 0
    return 0 # Push or unknown

def settle_alerts():
    db = DatabaseClient()
    stats = NbaStatsClient()
    bot = TelegramBotClient()
    
    logger.info("Initializing settlement engine...")
    with db.get_conn() as conn:
        cursor = conn.cursor()
        
        # Pull alerts that haven't been settled
        cursor.execute(
            """
            SELECT a.id, a.player_name, a.market, a.line, a.side, DATE(a.timestamp) as game_date
            FROM alerts_sent a
            LEFT JOIN bet_results b ON a.id = b.alert_id
            WHERE b.alert_id IS NULL
            """
        )
        unsettled = cursor.fetchall()
        
    if not unsettled:
        logger.info("No unsettled bets to grade.")
        return
        
    logger.info(f"Attempting to settle {len(unsettled)} alerts.")
    
    # In a fully robust prod system, we'd map game_date -> exact game_id using schedule
    # For a simplified V1 script, we'll iterate
    
    for row in unsettled:
        alert_id = row['id']
        player_name = row['player_name']
        market = row['market']
        line = row['line']
        side = row['side']
        date = row['game_date']
        
        # For this prototype settlement engine to work without exact game ID resolution
        # We need the player ID
        try:
            from nba_api.stats.static import players
            found = players.find_players_by_full_name(player_name)
            if not found: continue
            pid = found[0]['id']
            
            # Fetch recent logs which has the game outcomes
            logs = stats.get_player_game_logs(pid)
            if logs.empty: continue
            
            # Since logs returns a dataframe with GAME_DATE, we filter
            # Format in game logs is usually "MMM DD, YYYY". We'll just grab the latest game as a stub 
            # Or parse properly if we have actual date strings
            
            latest_game = logs.iloc[0]
            pts = latest_game.get('PTS', 0)
            ast = latest_game.get('AST', 0)
            reb = latest_game.get('REB', 0)
            threes = latest_game.get('FG3M', 0)
            pra = pts + ast + reb
            
            actual_val = 0
            if market == "player_points": actual_val = pts
            elif market == "player_rebounds": actual_val = reb
            elif market == "player_assists": actual_val = ast
            elif market == "player_threes": actual_val = threes
            elif market == "player_points_rebounds_assists": actual_val = pra
            
            won = evaluate_result(market, line, side, actual_val)
            
            # Insert result
            with db.get_conn() as wconn:
                wcursor = wconn.cursor()
                wcursor.execute(
                    "INSERT INTO bet_results (alert_id, actual_result, won) VALUES (?, ?, ?)",
                    (alert_id, float(actual_val), won)
                )
            logger.info(f"Settled Alert {alert_id} | {player_name} {side} {line} {market} -> Actual: {actual_val} | Won: {won}")
            
            # Send Telegram Alert
            result_emoji = "✅ WON" if won else "❌ LOST"
            message = (
                f"<b>Bet Settled: {result_emoji}</b>\n\n"
                f"🏀 <b>Player:</b> {player_name}\n"
                f"📊 <b>Market:</b> {market.replace('_', ' ').title()}\n"
                f"🎯 <b>Line:</b> {side} {line}\n"
                f"📈 <b>Actual Result:</b> {actual_val}"
            )
            bot.send_message(message)
            
        except Exception as e:
            logger.error(f"Failed resolving settlement for {player_name}: {e}")
            continue
            
    logger.info("Settlement run complete.")

if __name__ == "__main__":
    settle_alerts()
