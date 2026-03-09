import sqlite3
import os
from contextlib import contextmanager
from src.config import DB_PATH
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

class DatabaseClient:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.commit()
            conn.close()

    def _init_db(self):
        schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
        if not os.path.exists(schema_path):
            logger.warning(f"Schema not found at {schema_path}")
            return
            
        with open(schema_path, 'r') as f:
            schema = f.read()

        with self.get_conn() as conn:
            conn.executescript(schema)
            logger.info("Database schema initialized.")

    def insert_alert(self, player_name: str, market: str, line: float, side: str, edge: float, book: str, odds: float, stake: float = 0.0) -> int:
        with self.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO alerts_sent (player_name, market, line, side, edge, book, odds, stake)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (player_name, market, line, side, edge, book, odds, stake)
            )
            alert_id = cursor.lastrowid
            
            # Phase 3 CLV Tracking Link
            cursor.execute(
                """
                INSERT INTO clv_tracking (player_id, market, side, alert_odds, alert_time)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (player_name, market, side, odds)
            )
            
            return alert_id

    def check_recent_alert(self, player_name: str, market: str, line: float, side: str, edge: float) -> bool:
        with self.get_conn() as conn:
            # Re-alert only if line improves OR edge increases > 1%
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT edge FROM alerts_sent
                WHERE player_name = ? AND market = ? AND side = ? 
                AND abs(line - ?) <= 0.5
                AND date(timestamp) = date('now', 'localtime')
                ORDER BY timestamp DESC LIMIT 1
                """,
                (player_name, market, side, line)
            )
            row = cursor.fetchone()
            if not row:
                return False
                
            last_edge = row['edge']
            if edge - last_edge > 0.01:
                return False # Allow re-alert because edge improved > 1%
                
            return True
            
    def get_unsettled_clv(self):
        with self.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM clv_tracking WHERE closing_odds IS NULL")
            return [dict(r) for r in cursor.fetchall()]
            
    def update_clv_closing_line(self, track_id: int, closing_odds: float, implied_closing: float, implied_alert: float):
        clv = implied_closing - implied_alert
        with self.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE clv_tracking
                SET closing_odds = ?, closing_time = CURRENT_TIMESTAMP, clv = ?
                WHERE id = ?
                """,
                (closing_odds, clv, track_id)
            )

    def insert_line_history(self, player_name: str, market: str, bookmaker: str, line: float, side: str, odds: float, implied_prob: float):
        with self.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO line_history (player_name, market, bookmaker, line, side, odds, implied_prob)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (player_name, market, bookmaker, line, side, odds, implied_prob)
            )

    def init_bookmaker_profiles(self):
        profiles = [
            ("pinnacle", "sharp"),
            ("circa", "sharp"),
            ("draftkings", "rec"),
            ("fanduel", "rec"),
            ("betmgm", "rec"),
            ("caesars", "rec"),
            ("bovada", "rec"),
            ("betrivers", "rec")
        ]
        with self.get_conn() as conn:
            cursor = conn.cursor()
            for book, role in profiles:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO bookmaker_profiles (bookmaker, role)
                    VALUES (?, ?)
                    """,
                    (book, role)
                )

    def get_bookmaker_role(self, bookmaker: str) -> str:
        with self.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT role FROM bookmaker_profiles WHERE bookmaker = ? COLLATE NOCASE", (bookmaker,))
            row = cursor.fetchone()
            if row:
                return row['role']
            return "neutral"

    def insert_line_history_batch(self, records: list):
        with self.get_conn() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                """
                INSERT INTO line_history (player_name, market, bookmaker, line, side, odds, implied_prob)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                records
            )

    def get_market_metrics(self, player_name: str, market: str, line: float, side: str) -> dict:
        # Phase 5: Steam detection, velocity, and dispersion
        with self.get_conn() as conn:
            cursor = conn.cursor()
            # Get data from last 60 minutes
            cursor.execute(
                """
                SELECT bookmaker, implied_prob, timestamp 
                FROM line_history 
                WHERE player_name = ? AND market = ? AND line = ? AND side = ?
                  AND timestamp >= datetime('now', '-60 minute')
                ORDER BY timestamp ASC
                """,
                (player_name, market, line, side)
            )
            rows = cursor.fetchall()

        if not rows:
            return {"steam_flag": False, "velocity": 0.0, "dispersion": 0.0}

        import pandas as pd
        df = pd.DataFrame(rows, columns=['bookmaker', 'implied_prob', 'timestamp'])
        
        if df.empty or len(df) < 2:
            return {"steam_flag": False, "velocity": 0.0, "dispersion": 0.0}
            
        # Current dispersion across books (using most recent entry per book)
        latest = df.groupby('bookmaker').last()
        dispersion = 0.0
        if len(latest) > 1:
            dispersion = latest['implied_prob'].std()
            if pd.isna(dispersion): dispersion = 0.0
            
        # Velocity and Steam (did 3+ books move > 2% implied in same direction?)
        # Simplistic V1 approach: Look at first vs last implied_prob for each book
        first = df.groupby('bookmaker').first()
        changes = latest['implied_prob'] - first['implied_prob']
        
        velocity = changes.mean() if not changes.empty else 0.0
        
        # Steam flag: 3+ books moving > 0.02
        steam_books = changes[changes > 0.02]
        steam_flag = len(steam_books) >= 3
        
        return {
            "steam_flag": steam_flag,
            "velocity": float(velocity),
            "dispersion": float(dispersion)
        }
