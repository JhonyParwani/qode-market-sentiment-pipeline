"""
Runs multiple hashtag/cashtag scrape sessions concurrently.

Threads, not multiprocessing: each session is I/O-bound (waiting on
network/page-render, not CPU), and Selenium's WebDriver instances aren't
easily picklable across process boundaries anyway. A ThreadPoolExecutor
with one Chrome instance per worker gets the real bottleneck (wall-clock
time waiting on X to respond) parallelized without fighting the GIL, since
nearly all the time in each thread is spent inside blocking I/O calls that
release it.

Worker count is deliberately capped low (default 3) rather than maxed out
to core count — more concurrent sessions from behind the same network path
increases detection risk (see rate_limiter.py), so this trades some wall
-clock time for a lower chance of the whole run getting blocked partway
through, which is the worse failure mode.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

from src.scraper.twitter_scraper import TwitterScraper
from src.scraper.schema import RawTweet
from src.storage.parquet_store import ParquetStore
from src.utils.config import SCRAPER
from src.utils.logger import get_logger

logger = get_logger(__name__, log_file="scraper.log")


def _run_single_query(query: str, tag: str, target: int) -> List[RawTweet]:
    results = []
    try:
        with TwitterScraper() as scraper:
            for tweet in scraper.scrape_query(query, tag, target):
                results.append(tweet)
    except Exception:
        logger.exception(f"Worker for tag '{tag}' failed.")
    return results


<<<<<<< HEAD
def run_concurrent_scrape(max_workers: int = 3, batch_flush_size: int = 200) -> dict:
    """Returns {tag: tweets_collected} so a shortfall against
    tweets_per_hashtag is visible per-tag rather than only as a total."""
    store = ParquetStore()
    jobs = [(f"%23{tag}", tag, SCRAPER.tweets_per_hashtag) for tag in SCRAPER.hashtags]
    jobs += [(f"%24{tag}", tag, min(500, SCRAPER.tweets_per_hashtag)) for tag in SCRAPER.cashtags]

    results_per_tag = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_run_single_query, q, t, n): (t, n) for q, t, n in jobs}
        for future in as_completed(futures):
            tag, target = futures[future]
            tweets = future.result()
            results_per_tag[tag] = len(tweets)
            shortfall_note = "" if len(tweets) >= target else f" (short of {target} target)"
            logger.info(f"Worker for '{tag}' collected {len(tweets)} tweets{shortfall_note}.")
            for i in range(0, len(tweets), batch_flush_size):
                store.write_batch(tweets[i:i + batch_flush_size])

    total_written = sum(results_per_tag.values())
    logger.info(f"Concurrent scrape complete: {total_written} tweets written across {len(results_per_tag)} tags.")
    return results_per_tag
=======
def run_concurrent_scrape(max_workers: int = 3, batch_flush_size: int = 200) -> int:
    store = ParquetStore()
    per_query_target = max(
        1, SCRAPER.target_tweet_count // (len(SCRAPER.hashtags) + len(SCRAPER.cashtags))
    )
    jobs = [(f"%23{tag}", tag, per_query_target) for tag in SCRAPER.hashtags]
    jobs += [(f"%24{tag}", tag, per_query_target) for tag in SCRAPER.cashtags]

    total_written = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_run_single_query, q, t, n): t for q, t, n in jobs}
        for future in as_completed(futures):
            tag = futures[future]
            tweets = future.result()
            logger.info(f"Worker for '{tag}' collected {len(tweets)} tweets.")
            for i in range(0, len(tweets), batch_flush_size):
                total_written += store.write_batch(tweets[i:i + batch_flush_size])

    logger.info(f"Concurrent scrape complete: {total_written} tweets written.")
    return total_written
>>>>>>> origin/main


if __name__ == "__main__":
    run_concurrent_scrape()
