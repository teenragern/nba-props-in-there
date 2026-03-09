import requests
from typing import List, Dict, Any
from src.utils.retry import retry_with_backoff
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

class InjuryClient:
    def __init__(self):
        self.source_url = "https://www.cbssports.com/nba/injuries/"

    @retry_with_backoff(retries=3, backoff_in_seconds=2)
    def get_injuries(self) -> List[Dict[str, str]]:
        logger.info("Fetching injury report")
        # Stub for V1
        return []
        
    def normalize_status(self, raw_status: str) -> str:
        status = raw_status.lower() if raw_status else ""
        if "out" in status: return "Out"
        if "doubtful" in status: return "Doubtful"
        if "questionable" in status or "game time decision" in status or "gtd" in status: return "Questionable"
        if "probable" in status: return "Probable"
        return "Unknown"
