"""
Parquet storage layer.

Why Parquet over CSV/JSON/SQLite for this use case:
- Columnar + Snappy compression: tweet text is the only wide column, so a
  columnar format lets numeric aggregation (signals, engagement stats) scan
  only the columns it needs instead of the whole row — this matters once
  you're at the "10x more data" scale the assignment asks about.
- Native support for partitioning (scrape_date / primary_hashtag) means the
  analysis layer can prune partitions with a filter pushdown instead of
  loading everything into memory.
- Schema enforcement catches malformed records at write time rather than
  silently corrupting a CSV.

Why batched writes instead of one row at a time:
Every write() call in pyarrow has fixed overhead. Buffering ~200 tweets in
the scraper before flushing (see twitter_scraper.py) amortizes that cost and
also means a crash mid-session loses at most one batch, not the whole run.
"""

from pathlib import Path
from typing import Iterable

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.scraper.schema import RawTweet
from src.utils.config import DATA_RAW, STORAGE
from src.utils.logger import get_logger

logger = get_logger(__name__)

SCHEMA = pa.schema([
    ("tweet_id", pa.string()),
    ("username", pa.string()),
    ("display_name", pa.string()),
    ("content", pa.string()),
    ("timestamp", pa.timestamp("us", tz="UTC")),
    ("like_count", pa.int32()),
    ("retweet_count", pa.int32()),
    ("reply_count", pa.int32()),
    ("view_count", pa.float64()),  # nullable int -> float64 to allow NaN cleanly
    ("hashtags", pa.list_(pa.string())),
    ("mentions", pa.list_(pa.string())),
    ("primary_hashtag", pa.string()),
    ("is_reply", pa.bool_()),
    ("lang", pa.string()),
    ("scraped_at", pa.timestamp("us", tz="UTC")),
    ("scrape_date", pa.string()),
    ("engagement_score", pa.int32()),
])


class ParquetStore:
    def __init__(self, base_path: Path = DATA_RAW, config=STORAGE):
        self.base_path = base_path
        self.config = config

    def write_batch(self, tweets: Iterable[RawTweet]) -> int:
        rows = [t.to_dict() for t in tweets]
        if not rows:
            return 0

        df = pd.DataFrame(rows)
        table = pa.Table.from_pandas(df, schema=SCHEMA, preserve_index=False)

        pq.write_to_dataset(
            table,
            root_path=str(self.base_path),
            partition_cols=self.config.partition_cols,
            compression=self.config.compression,
            existing_data_behavior="overwrite_or_ignore",
        )
        logger.info(f"Flushed {len(rows)} tweets to {self.base_path}")
        return len(rows)

    def load(self, columns: list = None, filters: list = None) -> pd.DataFrame:
        """
        `filters` uses pyarrow's predicate pushdown format, e.g.
        [("primary_hashtag", "=", "nifty50")] — this avoids reading
        partitions you don't need at all, not just filtering after loading.
        """
        if not any(self.base_path.rglob("*.parquet")):
            logger.warning(f"No parquet files found under {self.base_path}")
            return pd.DataFrame()

        return pd.read_parquet(
            self.base_path, columns=columns, filters=filters, engine="pyarrow"
        )
