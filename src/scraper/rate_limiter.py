"""
Anti-bot / rate-limit handling.

X doesn't publish a scraping rate limit (there isn't a contract here — this
isn't the API), so "handling rate limiting creatively" in practice means:
reduce the odds of being flagged as a bot in the first place, and degrade
gracefully (cooldown, backoff, eventually stop) if it happens anyway rather
than hammering a wall and getting the account/IP burned.

Three layers:
1. Randomized human-like pacing (never a fixed sleep interval).
2. A forced cooldown every N scrolls, independent of whether anything
   looks wrong yet — cheap insurance.
3. Exponential backoff with jitter triggered by detected soft-block
   signals (login walls, "Rate limit exceeded" toasts, CAPTCHA elements).
"""

import random
import time
from src.utils.config import SCRAPER
from src.utils.logger import get_logger

logger = get_logger(__name__)


class RateLimiter:
    def __init__(self, config=SCRAPER):
        self.config = config
        self.scroll_count = 0
        self.consecutive_soft_blocks = 0

    def human_pause(self):
        """Sleep a randomized interval instead of a fixed one — fixed
        intervals are one of the easiest bot signatures to fingerprint."""
        delay = random.uniform(self.config.scroll_pause_min_sec, self.config.scroll_pause_max_sec)
        time.sleep(delay)

    def register_scroll(self):
        self.scroll_count += 1
        if self.scroll_count % self.config.scrolls_before_cooldown == 0:
            logger.info(
                f"Hit {self.scroll_count} scrolls — taking a {self.config.session_cooldown_sec}s "
                "cooldown before continuing."
            )
            time.sleep(self.config.session_cooldown_sec)

    def register_soft_block(self):
        """Call this when the scraper detects a rate-limit/CAPTCHA/login-wall
        signal. Backs off exponentially and gives up after too many in a row
        rather than looping forever against a wall."""
        self.consecutive_soft_blocks += 1
        backoff = min(60 * (2 ** self.consecutive_soft_blocks), 900) + random.uniform(0, 10)
        logger.warning(
            f"Soft block detected (#{self.consecutive_soft_blocks}). "
            f"Backing off {backoff:.0f}s."
        )
        time.sleep(backoff)
        return self.consecutive_soft_blocks < 5  # False => caller should abort session

    def register_success(self):
        self.consecutive_soft_blocks = 0

    def should_continue(self) -> bool:
        return self.scroll_count < self.config.max_scrolls_per_session
