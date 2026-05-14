import os
import functools
from diskcache import Cache

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(PROJECT_ROOT, '.wiki_cache')

cache = Cache(CACHE_DIR)

CACHE_ENABLED = os.environ.get('WIKI_CACHE_ENABLED', '1').lower() in ('1', 'true', 'yes')

WIKI_UA = (
    'MIT OCW Bot/1.0 '
    '(https://meta.wikimedia.org/wiki/Wiki_MIT; andrew.lih@gmail.com) '
    'ContentGapResearch'
)

ERROR_TTL = 60


def persistent_wiki_cache(ttl=None):
    """Decorator that caches function results using diskcache.

    Args:
        ttl: Time-to-live in seconds. None = persist indefinitely.

    Supports:
        - WIKI_CACHE_ENABLED env var (default: True) to bypass all caching.
        - force_refresh=True kwarg on the decorated function to bypass
          cache for a single invocation.
        - Automatic short TTL (60s) for failed results (None or error dicts)
          so transient failures don't poison the cache.

    Usage:
        @persistent_wiki_cache(ttl=604800)  # 7 days
        def fetch_popular_pages(project):
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            force_refresh = kwargs.pop('force_refresh', False)

            if not CACHE_ENABLED:
                return func(*args, **kwargs)

            key = (
                func.__module__,
                func.__qualname__,
                args,
                tuple(sorted((k, v) for k, v in kwargs.items())),
            )

            if not force_refresh and key in cache:
                return cache[key]

            result = func(*args, **kwargs)

            if _is_error(result):
                cache.set(key, result, expire=ERROR_TTL)
            else:
                cache.set(key, result, expire=ttl)

            return result
        return wrapper
    return decorator


def _is_error(result):
    if result is None:
        return True
    if isinstance(result, dict) and result.get('error'):
        return True
    if isinstance(result, list) and len(result) == 1 and isinstance(result[0], dict) and result[0].get('error'):
        return True
    return False
