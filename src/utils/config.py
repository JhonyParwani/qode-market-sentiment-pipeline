"""
Single place for every tunable in the pipeline. Nothing below should be
hardcoded again anywhere else in the codebase — import from here instead.
"""

from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
DATA_SAMPLE = PROJECT_ROOT / "data" / "sample"

for _dir in (DATA_RAW, DATA_PROCESSED, DATA_SAMPLE):
    _dir.mkdir(parents=True, exist_ok=True)


@dataclass
class ScraperConfig:
    # Core Indian market hashtags/cashtags from the assignment brief, plus a
    # few high-signal additions I found by manually browsing X — #stockmarketindia
    # and $NIFTY/$BANKNIFTY cashtags surface a materially different (more
    # retail-trader) slice of the conversation than the hashtags alone.
    hashtags: list = field(default_factory=lambda: [
        "nifty50", "sensex", "intraday", "banknifty",
"stockmarketindia", "niftytrading",
    ])
    cashtags: list = field(default_factory=lambda: ["NIFTY", "BANKNIFTY", "SENSEX"])

    # Per-hashtag target, not a total split across queries. The client asked
    # explicitly for 2,000 real tweets PER hashtag, which is a materially
    # bigger ask than 2,000 total (12,000+ tweets across the 6 tags here) —
    # see docs/APPROACH.md for the honest note on why some low-volume tags
    # may not hit this number inside a 24h window on live data, and what to
    # do about it rather than fabricate the shortfall.
    tweets_per_hashtag: int = 2000
    lookback_hours: int = 24

    # Selenium tends to get flagged fast on X if you hammer it, and that risk
    # goes up materially at this volume vs. the original 2,000-total target.
    # These knobs exist specifically to be tuned down under a stricter proxy
    # or up on a residential IP with a warmed-up account.
    scroll_pause_min_sec: float = 2.5
    scroll_pause_max_sec: float = 5.5
    # Getting to 2,000 unique tweets on one tag can take a lot more than 400
    # scrolls once X starts re-showing already-seen tweets on refresh/scroll-back
    # (common past a few hundred scrolls). Raised the ceiling but paired it
    # with a stall detector in the scraper (see twitter_scraper.py) so a
    # session that's stopped finding new tweets gives up instead of burning
    # scrolls indefinitely.
    max_scrolls_per_session: int = 1500
    session_cooldown_sec: int = 90       # forced pause every N scrolls
    scrolls_before_cooldown: int = 40
    stall_scroll_limit: int = 25         # abort a query if this many scrolls pass with zero new tweets
    headless: bool = True
    page_load_timeout_sec: int = 30

    # Market hours (IST) — used to weight/flag tweets posted during live
    # trading vs after-hours commentary, since the two have different
    # signal quality for intraday strategies.
    market_open_hour: int = 9
    market_open_minute: int = 15
    market_close_hour: int = 15
    market_close_minute: int = 30


@dataclass
class StorageConfig:
    partition_cols: list = field(default_factory=lambda: ["scrape_date", "primary_hashtag"])
    compression: str = "snappy"
    dedup_key_cols: list = field(default_factory=lambda: ["tweet_id"])
    near_dup_similarity_threshold: float = 0.92  # for retweet-phrased near-duplicates


@dataclass
class SignalConfig:
    tfidf_max_features: int = 5000
    tfidf_ngram_range: tuple = (1, 2)
    rolling_window_minutes: int = 15
    confidence_min_sample_size: int = 20  # below this, widen the CI heavily
    engagement_weight: float = 0.6         # weight given to engagement-weighted sentiment
    volume_weight: float = 0.4             # weight given to raw mention-volume z-score


SCRAPER = ScraperConfig()
STORAGE = StorageConfig()
SIGNAL = SignalConfig()
