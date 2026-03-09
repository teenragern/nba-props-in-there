from src.clients.odds_api import OddsApiClient
from src.data.db import DatabaseClient
from src.utils.logging_utils import get_logger
from datetime import datetime
import dateutil.parser

logger = get_logger(__name__)

def sync_events():
    client = OddsApiClient()
    db = DatabaseClient()
    
    events = client.get_events()
    logger.info(f"Fetched {len(events)} events.")
    
    with db.get_conn() as conn:
        cursor = conn.cursor()
        for event in events:
            game_id = event['id']
            home_team = event['home_team']
            away_team = event['away_team']
            commence_time = event['commence_time']
            dt = dateutil.parser.isoparse(commence_time)
            
            status = 'upcoming'
            if dt.timestamp() < datetime.now().timestamp():
                status = 'started'
                
            cursor.execute(
                """
                INSERT OR REPLACE INTO games (game_id, home_team, away_team, commence_time, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (game_id, home_team, away_team, commence_time, status)
            )
            
    logger.info("Events synchronized to database.")

if __name__ == "__main__":
    sync_events()
