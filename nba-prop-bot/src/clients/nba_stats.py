import time
import pandas as pd
from typing import Dict, Any, List
from nba_api.stats.endpoints import playergamelogs, leaguedashteamstats, commonplayerinfo, boxscoretraditionalv2
from src.utils.retry import retry_with_backoff
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

import os
import sqlite3
import json
from datetime import datetime

class NbaStatsClient:
    def __init__(self, season: str = "2023-24"):
        self.season = season
        self.cache_db = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'stats_cache.db')
        self._init_cache()
        
    def _init_cache(self):
        os.makedirs(os.path.dirname(self.cache_db), exist_ok=True)
        with sqlite3.connect(self.cache_db) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS player_logs_cache (
                    player_id INTEGER PRIMARY KEY,
                    date_fetched TEXT,
                    data_json TEXT
                )
            """)

    @retry_with_backoff(retries=3, backoff_in_seconds=2)
    def get_player_game_logs(self, player_id: int) -> pd.DataFrame:
        today = datetime.now().strftime('%Y-%m-%d')
        
        with sqlite3.connect(self.cache_db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT date_fetched, data_json FROM player_logs_cache WHERE player_id = ?", (player_id,))
            row = cursor.fetchone()
            if row and row[0] == today:
                import io
                return pd.read_json(io.StringIO(row[1]))
                
        logger.info(f"Fetching game logs for player {player_id}")
        logs = playergamelogs.PlayerGameLogs(
            player_id_nullable=player_id, 
            season_nullable=self.season
        )
        time.sleep(0.6)
        df = logs.get_data_frames()[0]
        
        with sqlite3.connect(self.cache_db) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO player_logs_cache (player_id, date_fetched, data_json) VALUES (?, ?, ?)",
                (player_id, today, df.to_json())
            )
            
        return df

    @retry_with_backoff(retries=3, backoff_in_seconds=2)
    def get_team_stats(self) -> pd.DataFrame:
        logger.info("Fetching team stats (pace, ratings)")
        stats = leaguedashteamstats.LeagueDashTeamStats(
            season=self.season,
            measure_type_detailed_defense='Advanced'
        )
        time.sleep(0.6)
        return stats.get_data_frames()[0]
        
    @retry_with_backoff(retries=3, backoff_in_seconds=2)
    def get_player_info(self, player_id: int) -> Dict[str, Any]:
        info = commonplayerinfo.CommonPlayerInfo(player_id=player_id)
        time.sleep(0.6)
        return info.get_dict()
        
    @retry_with_backoff(retries=3, backoff_in_seconds=2)
    def get_box_score(self, game_id: str) -> pd.DataFrame:
        logger.info(f"Fetching box score for game {game_id}")
        # Need to format game id carefully for nba api (requires 00 prefix)
        if not str(game_id).startswith('00'):
            logger.warning(f"Game ID {game_id} may not be NBA API format.")
        box = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id)
        time.sleep(0.6)
        return box.get_data_frames()[0]
