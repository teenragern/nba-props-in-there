import time
import functools
from requests.exceptions import RequestException

def retry_with_backoff(retries=3, backoff_in_seconds=1, exceptions=(RequestException,)):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            x = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if x == retries:
                        raise
                    sleep = (backoff_in_seconds * 2 ** x)
                    time.sleep(sleep)
                    x += 1
        return wrapper
    return decorator
