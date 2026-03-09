import json
import os
import time
from typing import Any, Optional
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

class DiskCache:
    def __init__(self, cache_dir: str = ".cache", ttl_seconds: int = 3600):
        self.cache_dir = cache_dir
        self.ttl_seconds = ttl_seconds
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)

    def _get_path(self, key: str) -> str:
        safe_key = "".join([c if c.isalnum() else "_" for c in key])
        return os.path.join(self.cache_dir, f"{safe_key}.json")

    def get(self, key: str) -> Optional[Any]:
        path = self._get_path(key)
        if not os.path.exists(path): return None
            
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            if time.time() - data.get('timestamp', 0) > data.get('ttl', self.ttl_seconds):
                os.remove(path)
                return None
            return data.get('value')
        except Exception as e:
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        path = self._get_path(key)
        data = {
            'timestamp': time.time(),
            'ttl': ttl if ttl is not None else self.ttl_seconds,
            'value': value
        }
        try:
            with open(path, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            pass
