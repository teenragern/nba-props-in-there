from src.utils.logging_utils import get_logger
from src.clients.injuries import InjuryClient
from src.data.db import DatabaseClient
from datetime import datetime

logger = get_logger(__name__)

def sync_injuries():
    client = InjuryClient()
    db = DatabaseClient()
    
    logger.info("Syncing injury reports")
    
    reports = client.get_injuries()
    today = datetime.now().strftime('%Y-%m-%d')
    
    with db.get_conn() as conn:
        cursor = conn.cursor()
        for r in reports:
            cursor.execute(
                """
                INSERT OR REPLACE INTO injury_reports (game_date, player_name, team, status)
                VALUES (?, ?, ?, ?)
                """,
                (today, r['player'], r['team'], r['status'])
            )
            
    logger.info("Injury sync complete. (Currently stubbed out)")

if __name__ == "__main__":
    sync_injuries()
