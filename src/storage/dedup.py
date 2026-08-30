"""
Two-tier deduplication.

Tier 1 — exact: tweet_id is the platform's own primary key, so an exact
dupe means the same tweet was captured twice across overlapping hashtag
searches (very common — a #banknifty tweet often also has #nifty50).
This is an O(n) hash-set operation.

Tier 2 — near-duplicate: X's own native "quote-retweet with one word
changed" and copy-paste spam ("BUY NIFTY NOW 🚀🚀🚀" reposted by 40 bot
accounts) both survive tier 1 since each has a distinct tweet_id. This
tier uses MinHash locality-sensitive hashing instead of pairwise cosine
similarity — pairwise comparison is O(n^2) and doesn't scale past a few
thousand tweets, which defeats the point of the "10x more data" scalability
requirement. MinHash LSH gets this down to roughly O(n) with a tunable
recall/precision tradeoff via `near_dup_similarity_threshold`.
"""

import re
from typing import Iterable

import pandas as pd
from datasketch import MinHash, MinHashLSH

from src.utils.config import STORAGE
from src.utils.logger import get_logger

logger = get_logger(__name__)

_URL_RE = re.compile(r"http\S+")
_NON_WORD_RE = re.compile(r"[^\w\s]")
_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_for_hash(text: str) -> str:
    """Strip URLs, punctuation/emoji, and collapse whitespace before
    shingling. Two tweets that differ only in a trailing '!', an emoji, or
    their t.co tracking link are the same near-duplicate for our purposes —
    keeping punctuation in would fragment shingles on cosmetic differences
    and undercount real duplicates (copy-paste spam near-always varies
    punctuation/emoji slightly)."""
    text = _URL_RE.sub(" ", text.lower())
    text = _NON_WORD_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _shingle(text: str, k: int = 3) -> set:
    tokens = text.split()
    if len(tokens) < k:
        return {text}
    return {" ".join(tokens[i:i + k]) for i in range(len(tokens) - k + 1)}


def exact_dedup(df: pd.DataFrame, key_cols: list = None) -> pd.DataFrame:
    key_cols = key_cols or STORAGE.dedup_key_cols
    before = len(df)
    df = df.drop_duplicates(subset=key_cols, keep="first")
    logger.info(f"Exact dedup: {before} -> {len(df)} rows ({before - len(df)} removed)")
    return df


def near_duplicate_dedup(df: pd.DataFrame, threshold: float = None, num_perm: int = 64) -> pd.DataFrame:
    """
    Drops near-duplicate tweets using MinHash LSH, keeping the copy with the
    highest engagement (the "real" post, in the common case of a viral tweet
    getting copy-pasted by low-effort accounts).
    """
    threshold = threshold or STORAGE.near_dup_similarity_threshold
    if df.empty:
        return df

    lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
    minhashes = {}

    # Process highest-engagement tweets first so they "win" the LSH bucket
    # and get kept as the canonical copy.
    ordered = df.sort_values("engagement_score", ascending=False)
    keep_ids = []

    for _, row in ordered.iterrows():
        tid = row["tweet_id"]
        mh = MinHash(num_perm=num_perm)
        for shingle in _shingle(_normalize_for_hash(row["content"])):
            mh.update(shingle.encode("utf8"))

        similar = lsh.query(mh)
        if similar:
            continue  # near-duplicate of something already kept
        lsh.insert(tid, mh)
        minhashes[tid] = mh
        keep_ids.append(tid)

    before = len(df)
    result = df[df["tweet_id"].isin(keep_ids)]
    logger.info(f"Near-dup dedup: {before} -> {len(result)} rows ({before - len(result)} removed)")
    return result


def deduplicate(df: pd.DataFrame, near_duplicates: bool = True) -> pd.DataFrame:
    df = exact_dedup(df)
    if near_duplicates:
        df = near_duplicate_dedup(df)
    return df.reset_index(drop=True)
