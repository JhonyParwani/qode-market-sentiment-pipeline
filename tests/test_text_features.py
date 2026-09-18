import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import pytest

from src.signals.text_features import lexicon_sentiment_score, TextFeaturizer
from src.processing.cleaner import clean_content, detect_script, normalize_unicode


def test_lexicon_sentiment_bullish():
    score = lexicon_sentiment_score("nifty breakout, bullish rally incoming", emojis=["🚀"])
    assert score > 0


def test_lexicon_sentiment_bearish():
    score = lexicon_sentiment_score("banknifty breakdown, expecting crash", emojis=["📉"])
    assert score < 0


def test_lexicon_sentiment_neutral_with_no_lexicon_hits():
    score = lexicon_sentiment_score("watching the market today", emojis=[])
    assert score == 0.0


def test_lexicon_short_trading_slang_not_misread():
    # "short" should not be treated as generic-negative-English; it's neutral
    # trading terminology and only counted via the explicit lexicon entry.
    score = lexicon_sentiment_score("going short on nifty here", emojis=[])
    assert score < 0  # counted correctly as bearish via the trading lexicon, not skipped


def test_clean_content_strips_urls_and_emoji():
    raw = "Nifty rallying hard today 🚀🚀 check https://t.co/abc123"
    cleaned = clean_content(raw)
    assert "http" not in cleaned
    assert "🚀" not in cleaned
    assert "Nifty" in cleaned


def test_detect_script_devanagari():
    assert detect_script("बाजार आज मजबूत है") == "devanagari"


def test_detect_script_mixed():
    assert detect_script("kal market girega यार") == "devanagari_mixed"


def test_detect_script_latin():
    assert detect_script("nifty looking strong today") == "latin"


def test_featurizer_top_terms_nonempty():
    texts = pd.Series([
        "nifty breakout strong rally",
        "nifty breakout continues today",
        "banknifty support holding well",
    ])
    featurizer = TextFeaturizer()
    matrix = featurizer.fit_transform(texts)
    top = featurizer.top_terms(matrix, n=5)
    assert len(top) > 0
    assert all(isinstance(term, str) and isinstance(score, float) for term, score in top)


def test_featurizer_handles_too_few_docs():
    featurizer = TextFeaturizer()
    matrix = featurizer.fit_transform(pd.Series(["only one doc"]))
    assert matrix is None
    assert featurizer.top_terms(matrix) == []
