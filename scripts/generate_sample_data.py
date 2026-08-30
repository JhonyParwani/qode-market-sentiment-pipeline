"""
Generates a realistic synthetic sample dataset and runs it through the full
pipeline, producing the sample outputs committed under data/sample/.

Why this script exists: X actively blocks scraping from data-center IPs
(which is what any CI runner or cloud sandbox is on), so a live scrape
can't run in an automated/demo environment — it needs a real residential
session, exactly as the assignment's "creative anti-bot handling" section
implies. This script generates realistic-shaped data (same schema, same
statistical properties — engagement power-law, bursty volume, mixed-script
content) so the rest of the pipeline (storage, cleaning, dedup, signals,
plots) can be run and verified end-to-end without needing live credentials.

Run the real thing with: python -m src.scraper.twitter_scraper
"""

import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.scraper.schema import RawTweet
from src.storage.parquet_store import ParquetStore
from src.utils.logger import get_logger

logger = get_logger(__name__, log_file="sample_data.log")

random.seed(7)

HASHTAG_POOL = ["nifty50", "sensex", "intraday", "banknifty", "stockmarketindia", "niftytrading"]

BULLISH_TEMPLATES = [
    "Nifty breaking out above resistance, {tag} looking strong for tomorrow 🚀",
    "Banknifty holding support beautifully, bullish structure intact #{tag}",
    "Added more longs, this rally has legs. {tag}",
    "kal market phat sakta hai, buy on dips! #{tag}",
    "ATH incoming for sensex, don't fight the trend #{tag}",
    "Strong FII buying today, {tag} looking good 📈",
]
BEARISH_TEMPLATES = [
    "Nifty breakdown below support, expecting more downside #{tag}",
    "Booked losses today, this correction isn't over #{tag}",
    "banknifty crash ho gaya, stop loss hit on 3 positions #{tag}",
    "Bearish engulfing on daily chart, sell on rallies #{tag}",
    "FII selling pressure continues, {tag} weak 📉",
    "market bahut weak lag raha hai aaj, be careful #{tag}",
]
NEUTRAL_TEMPLATES = [
    "Watching {tag} closely today, range-bound so far",
    "RBI policy meet tomorrow, expecting volatility in {tag}",
    "Quiet session so far on {tag}, waiting for a clear setup",
    "Any views on {tag} for tomorrow's session? #{tag}",
    "Results season starting, keep an eye on {tag} earnings",
]

USERNAMES = [f"trader_{i:03d}" for i in range(1, 260)] + [
    "nifty_bulls_in", "banknifty_pro", "market_pandit", "dalalstreet_desi", "chart_wale_baba",
]


EXTRA_CLAUSES = [
    "", "", "",  # empty strings weighted in so not every tweet gets padding
    " eyeing {level} as the level to watch",
    " been trading since 9:15 today",
    " volumes are unusually high today",
    " let's see how the last hour plays out",
    " thoughts?",
    " what are you all doing here",
    " this is just my view, not advice",
    " {level} zone is key here",
    " closing above {level} would confirm it",
    " been a wild session honestly",
    " small position, managing risk",
]


def _pick_template(bucket_hour: int):
    # Slightly more bearish sentiment skew mid-session (arbitrary but
    # gives the sample data a believable, non-uniform sentiment curve
    # instead of flat noise).
    if 11 <= bucket_hour <= 13:
        weights = [0.3, 0.5, 0.2]
    else:
        weights = [0.45, 0.3, 0.25]
    bucket = random.choices(["bull", "bear", "neutral"], weights=weights)[0]
    templates = {"bull": BULLISH_TEMPLATES, "bear": BEARISH_TEMPLATES, "neutral": NEUTRAL_TEMPLATES}[bucket]
    return random.choice(templates)


def _compose_content(template: str, tag: str) -> str:
    """Real tweets on the same theme are still lexically distinct — same
    template text repeated verbatim across hundreds of tweets would be an
    unrealistic dataset (and would make the near-duplicate detector collapse
    it far more aggressively than it should on real data). Composing each
    tweet from a template + a randomized extra clause + a randomized price
    level gives the sample data believable lexical diversity while keeping
    a small, controlled fraction of genuine near-duplicates (injected
    separately below) for the dedup module to demonstrably catch."""
    level = random.choice([f"{n:,}" for n in range(19500, 24800, 25)])
    extra = random.choice(EXTRA_CLAUSES).format(level=level)
    content = template.format(tag=tag) + extra
    return content


def _synthetic_engagement():
    # Power-law-ish: most tweets get little engagement, a few go semi-viral.
    base = random.paretovariate(1.8)
    likes = min(int(base * 8), 15000)
    retweets = int(likes * random.uniform(0.05, 0.25))
    replies = int(likes * random.uniform(0.02, 0.15))
    return likes, retweets, replies


def generate(n: int = 2400) -> list[RawTweet]:
    now = datetime.now(timezone.utc)
    tweets = []
    for _ in range(n):
        minutes_ago = random.betavariate(1.5, 3) * 24 * 60  # skewed toward "more recent"
        ts = now - timedelta(minutes=minutes_ago)
        tag = random.choice(HASHTAG_POOL)
        template = _pick_template(ts.hour)
        content = _compose_content(template, tag)
        likes, retweets, replies = _synthetic_engagement()
        extra_tags = random.sample(HASHTAG_POOL, k=random.randint(0, 2))

        tweets.append(RawTweet(
            tweet_id=str(uuid.uuid4().int)[:19],
            username=random.choice(USERNAMES),
            display_name=random.choice(USERNAMES),
            content=content,
            timestamp=ts,
            like_count=likes,
            retweet_count=retweets,
            reply_count=replies,
            view_count=likes * random.randint(8, 20),
            hashtags=tuple(sorted(set([tag] + extra_tags))),
            mentions=tuple(),
            primary_hashtag=tag,
            is_reply=random.random() < 0.12,
            lang="hi" if "kal" in content or "ho gaya" in content or "lag raha" in content else "en",
        ))

    # Inject a small number of exact + near-duplicate tweets so the dedup
    # module has something real to remove and demonstrate in the sample output.
    for _ in range(int(n * 0.03)):
        original = random.choice(tweets)
        dup = RawTweet(
            tweet_id=str(uuid.uuid4().int)[:19],
            username=random.choice(USERNAMES),
            display_name=original.display_name,
            content=original.content + (" " if random.random() < 0.5 else ""),
            timestamp=original.timestamp + timedelta(seconds=random.randint(1, 300)),
            like_count=random.randint(0, 5),
            retweet_count=0,
            reply_count=0,
            view_count=random.randint(10, 100),
            hashtags=original.hashtags,
            mentions=tuple(),
            primary_hashtag=original.primary_hashtag,
            is_reply=False,
            lang=original.lang,
        )
        tweets.append(dup)

    return tweets


if __name__ == "__main__":
    store = ParquetStore()
    tweets = generate(2400)
    store.write_batch(tweets)
    logger.info(f"Generated and stored {len(tweets)} synthetic sample tweets.")
