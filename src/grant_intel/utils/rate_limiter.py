"""Rate limiting and retry logic for API calls."""

import logging
import time

import requests

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple rate limiter using token bucket."""

    def __init__(self, calls_per_second: float = 1.0):
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0.0

    def wait(self):
        """Block until enough time has passed since the last call."""
        now = time.monotonic()
        elapsed = now - self.last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_call = time.monotonic()


def request_with_retry(
    method: str,
    url: str,
    rate_limiter: RateLimiter | None = None,
    max_retries: int = 3,
    **kwargs,
) -> requests.Response:
    """Make an HTTP request with rate limiting and exponential backoff.

    Retries on 429 (rate limited) and 5xx (server error) responses.
    """
    if rate_limiter:
        rate_limiter.wait()

    for attempt in range(max_retries + 1):
        try:
            response = requests.request(method, url, timeout=30, **kwargs)

            if response.status_code == 429 or response.status_code >= 500:
                if attempt < max_retries:
                    wait_time = 2 ** (attempt + 1)
                    logger.warning(
                        "HTTP %d from %s, retrying in %ds (attempt %d/%d)",
                        response.status_code,
                        url,
                        wait_time,
                        attempt + 1,
                        max_retries,
                    )
                    time.sleep(wait_time)
                    continue
                response.raise_for_status()

            return response

        except requests.exceptions.ConnectionError:
            if attempt < max_retries:
                wait_time = 2 ** (attempt + 1)
                logger.warning(
                    "Connection error to %s, retrying in %ds (attempt %d/%d)",
                    url,
                    wait_time,
                    attempt + 1,
                    max_retries,
                )
                time.sleep(wait_time)
                continue
            raise

    raise requests.exceptions.RetryError(f"Failed after {max_retries} retries: {url}")
