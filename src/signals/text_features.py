"""
Text -> numerical feature conversion.

I went with a hybrid approach rather than a single method, because they
fail in different, complementary ways for this domain:

1. TF-IDF vectors: good for finding which *terms* are spiking right now
   (useful for a human dashboard — "why is sentiment moving? oh, 'RBI
   policy' just spiked"), but TF-IDF alone has no notion of polarity —
   "nifty crashes" and "nifty rallies" both just look like "nifty" being
   frequent.

2. A finance-specific lexicon score: generic sentiment lexicons (VADER,
   TextBlob) are tuned on product reviews/news and misread trading slang
   badly — "short" is negative-coded in general English but is neutral
   trading terminology; "bearish"/"bullish" aren't in general lexicons at
   all. A small domain lexicon fixes the cases that actually matter for
   this dataset instead of pulling in a heavyweight pretrained model.

Both are cheap enough to run over the full dataset (no GPU, no external
calls), which matters given the "no paid APIs" and performance constraints.
A transformer embedding model (e.g. sentence-transformers) would likely
score higher on raw sentiment accuracy, and is the natural next step if the
system gets a GPU budget — noted in docs/APPROACH.md.
"""

import re

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from src.utils.config import SIGNAL
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Small, hand-built finance/trading lexicon. Deliberately domain-specific
# rather than a generic sentiment wordlist — see module docstring.
BULLISH_TERMS = {
    "bullish", "buy", "long", "breakout", "rally", "surge", "upside", "target hit",
    "support held", "accumulate", "uptrend", "gap up", "all time high", "ath",
}
BEARISH_TERMS = {
    "bearish", "sell", "short", "breakdown", "crash", "correction", "downside",
    "resistance", "distribute", "downtrend", "gap down", "stop loss hit", "sl hit", "dump",
}
# Emoji carry real directional signal in this domain (see cleaner.py docstring)
BULLISH_EMOJI = {"🚀", "📈", "🟢", "💚", "🔥"}
BEARISH_EMOJI = {"📉", "🔴", "❤️‍🔥", "😰", "💀"}


def lexicon_sentiment_score(content_clean: str, emojis: list) -> float:
    """Returns a score in [-1, 1]. Not a probability — a bounded lexicon
    tally normalized by lexicon hits, which is what a rules-based scorer
    can honestly claim to produce."""
    text = content_clean.lower()
    bull_hits = sum(1 for term in BULLISH_TERMS if term in text)
    bear_hits = sum(1 for term in BEARISH_TERMS if term in text)
    bull_hits += sum(1 for e in emojis if e in BULLISH_EMOJI)
    bear_hits += sum(1 for e in emojis if e in BEARISH_EMOJI)

    total = bull_hits + bear_hits
    if total == 0:
        return 0.0
    return (bull_hits - bear_hits) / total


class TextFeaturizer:
    """Fits TF-IDF once on the current batch/window and exposes both the
    sparse matrix (for downstream ML if needed) and top-term summaries
    (for the dashboard)."""

    def __init__(self, config=SIGNAL):
        self.config = config
        self.vectorizer = TfidfVectorizer(
            max_features=config.tfidf_max_features,
            ngram_range=config.tfidf_ngram_range,
            min_df=2,
            stop_words="english",
            token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z]+\b",  # ignores pure-numeric noise, keeps Latin-script tokens
        )
        self._fitted = False

    def fit_transform(self, texts: pd.Series):
        if len(texts) < 2:
            logger.warning("Too few documents to fit TF-IDF meaningfully.")
            return None
        matrix = self.vectorizer.fit_transform(texts.fillna(""))
        self._fitted = True
        return matrix

    def top_terms(self, matrix, n: int = 15) -> list[tuple[str, float]]:
        if not self._fitted or matrix is None:
            return []
        scores = np.asarray(matrix.sum(axis=0)).ravel()
        terms = self.vectorizer.get_feature_names_out()
        top_idx = np.argsort(scores)[::-1][:n]
        return [(terms[i], float(scores[i])) for i in top_idx]


def add_sentiment_features(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["sentiment_score"] = df.apply(
        lambda r: lexicon_sentiment_score(r["content_clean"], r["emojis"]), axis=1
    )
    df["sentiment_label"] = pd.cut(
        df["sentiment_score"], bins=[-1.01, -0.2, 0.2, 1.01], labels=["bearish", "neutral", "bullish"]
    )
    return df
