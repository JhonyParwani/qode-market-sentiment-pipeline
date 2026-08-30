"""
Data contract for a single scraped tweet.

I used a slotted dataclass instead of a plain dict for two reasons:
1. __slots__ cuts per-object memory ~40-50% vs a dict-backed instance,
   which matters when you're holding tens of thousands of these in memory
   during a scrape session before they're flushed to Parquet.
2. A dataclass gives every downstream module (dedup, cleaning, signals) a
   typed contract instead of hoping the dict keys line up.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass(slots=True)
class RawTweet:
    tweet_id: str                  # X's internal status id — primary dedup key
    username: str
    display_name: str
    content: str
    timestamp: datetime            # UTC
    like_count: int
    retweet_count: int
    reply_count: int
    view_count: Optional[int]
    hashtags: tuple                # tuple, not list — hashable, needed for set-based dedup
    mentions: tuple
    primary_hashtag: str           # which search query surfaced this tweet
    is_reply: bool
    lang: Optional[str]
    scraped_at: datetime = None

    def __post_init__(self):
        if self.scraped_at is None:
            object.__setattr__(self, "scraped_at", datetime.now(timezone.utc))

    @property
    def engagement_score(self) -> int:
        # Replies weighted highest — a reply is a stronger revealed-preference
        # signal than a like, and cheaper to fake at scale than a retweet
        # but still costs the user more effort than a like.
        return self.like_count + 2 * self.retweet_count + 3 * self.reply_count

    @property
    def scrape_date(self) -> str:
        return self.timestamp.strftime("%Y-%m-%d")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["hashtags"] = list(self.hashtags)
        d["mentions"] = list(self.mentions)
        d["scrape_date"] = self.scrape_date
        d["engagement_score"] = self.engagement_score
        return d
