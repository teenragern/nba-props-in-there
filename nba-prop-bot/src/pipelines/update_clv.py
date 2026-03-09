from src.utils.logging_utils import get_logger
from src.data.db import DatabaseClient
from src.clients.odds_api import OddsApiClient
from src.models.devig import decimal_to_implied_prob

logger = get_logger(__name__)

def update_clv_lines():
    db = DatabaseClient()
    odds_client = OddsApiClient()

    # Get unsettled alerts
    unsettled = db.get_unsettled_clv()
    if not unsettled:
        logger.info("No unsettled CLV trackers found.")
        return

    logger.info(f"Looking for closing lines for {len(unsettled)} items...")

    # Fetch fresh odds (we'd filter this to specific game IDs in prod, grabbing all for now)
    try:
        events = odds_client.get_events()
    except Exception as e:
        logger.error(f"Failed to fetch events for CLV: {e}")
        return

    for item in unsettled:
        player = item['player_id']
        market = item['market']
        side = item['side']
        track_id = item['id']
        alert_odds = item['alert_odds']
        
        # Searching all events just to find Best Odds again for this exact player/market
        closing_odds_found = False
        closing_price = 0.0

        for event in events:
            if closing_odds_found: break
                
            try:
                odds_data = odds_client.get_event_odds(event_id=event['id'], markets=[market])
            except: continue
                
            bookmakers = odds_data.get('bookmakers', [])
            for book in bookmakers:
                for book_mkt in book.get('markets', []):
                    if book_mkt['key'] == market:
                        for outcome in book_mkt.get('outcomes', []):
                            if outcome.get('description') == player and outcome.get('name', '').lower() == side.lower():
                                closing_odds_found = True
                                price = outcome.get('price', 0.0)
                                if price > closing_price:
                                    closing_price = price
                                    
        if closing_odds_found and closing_price > 0:
            implied_closing = decimal_to_implied_prob(closing_price)
            implied_alert = decimal_to_implied_prob(alert_odds)
            db.update_clv_closing_line(track_id, closing_price, implied_closing, implied_alert)
            logger.info(f"Recorded closing line {closing_price} for Tracker ID {track_id}")

if __name__ == "__main__":
    update_clv_lines()
