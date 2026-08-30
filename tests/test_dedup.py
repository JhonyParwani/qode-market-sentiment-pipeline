import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import pytest

from src.storage.dedup import exact_dedup, near_duplicate_dedup, deduplicate


def _row(tweet_id, content, engagement=10):
    return {
        "tweet_id": tweet_id,
        "content": content,
        "engagement_score": engagement,
        "username": "user1",
    }


def test_exact_dedup_removes_repeated_ids():
    df = pd.DataFrame([_row("1", "nifty looking strong"), _row("1", "nifty looking strong"), _row("2", "banknifty weak")])
    result = exact_dedup(df)
    assert len(result) == 2
    assert set(result["tweet_id"]) == {"1", "2"}


def test_exact_dedup_keeps_distinct_ids():
    df = pd.DataFrame([_row("1", "a"), _row("2", "b"), _row("3", "c")])
    result = exact_dedup(df)
    assert len(result) == 3


def test_near_duplicate_dedup_collapses_similar_text():
    df = pd.DataFrame([
        _row("1", "Nifty breaking out above resistance today looking strong", engagement=500),
        _row("2", "Nifty breaking out above resistance today looking strong!", engagement=2),
        _row("3", "Completely unrelated tweet about banknifty support levels", engagement=50),
    ])
    result = near_duplicate_dedup(df, threshold=0.8)
    assert len(result) == 2
    # the higher-engagement duplicate should be the one kept
    assert "1" in set(result["tweet_id"])


def test_near_duplicate_dedup_empty_df():
    df = pd.DataFrame(columns=["tweet_id", "content", "engagement_score"])
    result = near_duplicate_dedup(df)
    assert result.empty


def test_deduplicate_pipeline_runs_both_tiers():
    df = pd.DataFrame([
        _row("1", "banknifty crash incoming be very careful out there today", engagement=100),
        _row("1", "banknifty crash incoming be very careful out there today", engagement=100),  # exact dup
        _row("2", "banknifty crash incoming be very careful out there today!!", engagement=5),  # near dup (punctuation only)
        _row("3", "totally different content about sensex rally", engagement=20),
    ])
    result = deduplicate(df)
    assert len(result) == 2
