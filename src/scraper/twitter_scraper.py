"""
Selenium-based scraper for X (Twitter) search results.

No official/paid API is used anywhere in this module, per the assignment
constraint — this drives a real browser against the public search UI
(https://x.com/search?q=...&f=live) the same way a human scrolling the page
would.

IMPORTANT — run this locally, not in a sandboxed CI environment:
X requires a logged-in session for search results beyond the first screen,
and outbound access to x.com. Set X_USERNAME / X_PASSWORD (or better,
X_AUTH_TOKEN, see README) as environment variables before running.

This file is written to run standalone: `python -m src.scraper.twitter_scraper`
"""

import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Iterator, Optional

from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.scraper.rate_limiter import RateLimiter
from src.scraper.schema import RawTweet
from src.utils.config import SCRAPER
from src.utils.logger import get_logger
<<<<<<< HEAD
from dotenv import load_dotenv

load_dotenv()
=======

>>>>>>> origin/main
logger = get_logger(__name__, log_file="scraper.log")

SEARCH_URL = "https://x.com/search?q={query}&f=live"
LOGIN_URL = "https://x.com/i/flow/login"

# Soft-block indicators to watch for in page source / DOM
SOFT_BLOCK_MARKERS = ["Rate limit exceeded", "Something went wrong", "captcha", "Try again later"]


def _build_driver(headless: bool = True) -> webdriver.Chrome:
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    # Standard desktop UA — the default Selenium UA string is itself a
    # well-known bot fingerprint, so this alone meaningfully reduces
    # detection rate.
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=opts)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    driver.set_page_load_timeout(SCRAPER.page_load_timeout_sec)
    return driver


class TwitterScraper:
    def __init__(self, config=SCRAPER):
        self.config = config
        self.limiter = RateLimiter(config)
        self.driver: Optional[webdriver.Chrome] = None
        self.seen_ids: set[str] = set()

    def __enter__(self):
        self.driver = _build_driver(headless=self.config.headless)
        self._login()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.driver:
            self.driver.quit()

    def _login(self):
        """
        Cookie-based auth is strongly preferred over username/password:
        it survives across runs without re-triggering X's login-flow bot
        checks every session. See README for how to export auth_token /
        ct0 from an authenticated browser session.
        """
        auth_token = os.environ.get("X_AUTH_TOKEN")
        ct0 = os.environ.get("X_CT0")
        if auth_token and ct0:
            self.driver.get("https://x.com")
            self.driver.add_cookie({"name": "auth_token", "value": auth_token, "domain": ".x.com"})
            self.driver.add_cookie({"name": "ct0", "value": ct0, "domain": ".x.com"})
            self.driver.refresh()
            logger.info("Authenticated via session cookies.")
            return

        username = os.environ.get("X_USERNAME")
        password = os.environ.get("X_PASSWORD")
        if not (username and password):
            raise EnvironmentError(
                "No credentials found. Set X_AUTH_TOKEN+X_CT0 (preferred) or "
                "X_USERNAME+X_PASSWORD as environment variables."
            )

        self.driver.get(LOGIN_URL)
        wait = WebDriverWait(self.driver, self.config.page_load_timeout_sec)
        user_input = wait.until(EC.presence_of_element_located((By.NAME, "text")))
        user_input.send_keys(username)
        self.driver.find_element(By.XPATH, "//span[text()='Next']").click()
        time.sleep(2)
        pass_input = wait.until(EC.presence_of_element_located((By.NAME, "password")))
        pass_input.send_keys(password)
        self.driver.find_element(By.XPATH, "//span[text()='Log in']").click()
        time.sleep(3)
        logger.info("Authenticated via username/password flow.")

    def _detect_soft_block(self) -> bool:
        page = self.driver.page_source
        return any(marker.lower() in page.lower() for marker in SOFT_BLOCK_MARKERS)

    def _parse_tweet_card(self, card, primary_hashtag: str) -> Optional[RawTweet]:
        try:
            link = card.find_element(By.XPATH, ".//a[contains(@href, '/status/')]")
            href = link.get_attribute("href")
            tweet_id_match = re.search(r"/status/(\d+)", href)
            if not tweet_id_match:
                return None
            tweet_id = tweet_id_match.group(1)
            if tweet_id in self.seen_ids:
                return None  # in-memory dedup during the session itself

            username_el = card.find_element(By.XPATH, ".//div[@dir='ltr']/span[contains(text(),'@')]")
            username = username_el.text.lstrip("@")

            content_el = card.find_element(By.XPATH, ".//div[@data-testid='tweetText']")
            content = content_el.text

            time_el = card.find_element(By.TAG_NAME, "time")
            timestamp = datetime.fromisoformat(time_el.get_attribute("datetime").replace("Z", "+00:00"))

            def _metric(testid: str) -> int:
                try:
                    el = card.find_element(By.XPATH, f".//div[@data-testid='{testid}']")
                    label = el.get_attribute("aria-label") or "0"
                    num = re.search(r"[\d,]+", label)
                    return int(num.group().replace(",", "")) if num else 0
                except NoSuchElementException:
                    return 0

            likes = _metric("like")
            retweets = _metric("retweet")
            replies = _metric("reply")

            hashtags = tuple(h.lower() for h in re.findall(r"#(\w+)", content))
            mentions = tuple(m.lower() for m in re.findall(r"@(\w+)", content))

            self.seen_ids.add(tweet_id)
            return RawTweet(
                tweet_id=tweet_id,
                username=username,
                display_name=username,  # display name parsing is brittle/optional; username suffices downstream
                content=content,
                timestamp=timestamp,
                like_count=likes,
                retweet_count=retweets,
                reply_count=replies,
                view_count=None,
                hashtags=hashtags,
                mentions=mentions,
                primary_hashtag=primary_hashtag,
                is_reply=content.strip().startswith("@"),
                lang=None,
            )
        except (NoSuchElementException, StaleElementReferenceException):
            return None

    def scrape_query(self, query: str, primary_hashtag: str, max_tweets: int) -> Iterator[RawTweet]:
        url = SEARCH_URL.format(query=query)
        self.driver.get(url)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.config.lookback_hours)
        collected = 0
        wait = WebDriverWait(self.driver, self.config.page_load_timeout_sec)

        try:
            wait.until(EC.presence_of_element_located((By.XPATH, "//article")))
        except TimeoutException:
            logger.warning(f"No results loaded for query '{query}' — skipping.")
            return

<<<<<<< HEAD
        scrolls_since_new_tweet = 0

=======
>>>>>>> origin/main
        while collected < max_tweets and self.limiter.should_continue():
            if self._detect_soft_block():
                should_retry = self.limiter.register_soft_block()
                if not should_retry:
<<<<<<< HEAD
                    logger.error(
                        f"Too many consecutive soft blocks on '{query}' — ending session with "
                        f"{collected}/{max_tweets} collected. This is expected behavior, not a bug: "
                        "see docs/APPROACH.md on honest shortfall reporting."
                    )
=======
                    logger.error("Too many consecutive soft blocks — ending session.")
>>>>>>> origin/main
                    return
                continue

            cards = self.driver.find_elements(By.XPATH, "//article")
<<<<<<< HEAD
            found_new_this_pass = False
=======
>>>>>>> origin/main
            for card in cards:
                tweet = self._parse_tweet_card(card, primary_hashtag)
                if tweet is None:
                    continue
                if tweet.timestamp < cutoff:
<<<<<<< HEAD
                    logger.info(
                        f"Reached {self.config.lookback_hours}h lookback boundary for '{query}' "
                        f"at {collected}/{max_tweets} tweets."
                    )
                    return
                found_new_this_pass = True
=======
                    logger.info(f"Reached {self.config.lookback_hours}h lookback boundary for '{query}'.")
                    return
>>>>>>> origin/main
                collected += 1
                self.limiter.register_success()
                yield tweet
                if collected >= max_tweets:
                    return

<<<<<<< HEAD
            # X's search timeline reshuffles/re-renders already-seen tweets once
            # you've scrolled past everything genuinely new for a hashtag —
            # without this check the loop would burn scrolls forever on a
            # low-volume tag instead of recognizing it's actually exhausted
            # the available real tweets for the lookback window.
            scrolls_since_new_tweet = 0 if found_new_this_pass else scrolls_since_new_tweet + 1
            if scrolls_since_new_tweet >= self.config.stall_scroll_limit:
                logger.warning(
                    f"'{query}' stalled — {scrolls_since_new_tweet} scrolls with no new tweets. "
                    f"Stopping at {collected}/{max_tweets}: this likely means the hashtag doesn't "
                    f"have {max_tweets} distinct tweets in the last {self.config.lookback_hours}h, "
                    "not a scraper bug. Report the real count, don't force it."
                )
                return

=======
>>>>>>> origin/main
            self.driver.execute_script("window.scrollBy(0, window.innerHeight * 2.5);")
            self.limiter.register_scroll()
            self.limiter.human_pause()

    def scrape_all(self) -> Iterator[RawTweet]:
<<<<<<< HEAD
        """
        Required hashtags (from the client's brief) each get the full
        `tweets_per_hashtag` target. Cashtags are bonus coverage, scraped at
        a lower target so they don't roughly double total runtime — they
        weren't part of what was explicitly asked for.
        """
        required = [(f"%23{tag}", tag, self.config.tweets_per_hashtag) for tag in self.config.hashtags]
        bonus = [(f"%24{tag}", tag, min(500, self.config.tweets_per_hashtag)) for tag in self.config.cashtags]

        for query, tag, target in required + bonus:
            logger.info(f"Scraping '{tag}' (target {target} tweets)...")
            collected_for_tag = 0
            for tweet in self.scrape_query(query, tag, target):
                collected_for_tag += 1
                yield tweet
            logger.info(f"Finished '{tag}': {collected_for_tag}/{target} tweets collected.")
=======
        per_query_target = max(
            1, self.config.target_tweet_count // (len(self.config.hashtags) + len(self.config.cashtags))
        )
        queries = [(f"%23{tag}", tag) for tag in self.config.hashtags]
        queries += [(f"%24{tag}", tag) for tag in self.config.cashtags]

        for query, tag in queries:
            logger.info(f"Scraping '{tag}' (target {per_query_target} tweets)...")
            yield from self.scrape_query(query, tag, per_query_target)
>>>>>>> origin/main


if __name__ == "__main__":
    from src.storage.parquet_store import ParquetStore

    store = ParquetStore()
    with TwitterScraper() as scraper:
        buffer = []
        for tweet in scraper.scrape_all():
            buffer.append(tweet)
            if len(buffer) >= 200:  # flush in batches — see storage module docstring for why
                store.write_batch(buffer)
                buffer = []
        if buffer:
            store.write_batch(buffer)
    logger.info("Scrape complete.")
