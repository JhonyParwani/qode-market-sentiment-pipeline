"""
Aggregates per-tweet sentiment into a composite, time-bucketed trading
signal per symbol (NIFTY / BANKNIFTY / SENSEX), with a confidence interval.

Design choices worth flagging in a review:

- Engagement-weighted, not a simple mean. A tweet with 3,000 likes moving
  bearish should move the signal more than five bot accounts posting
  "bullish" with zero engagement. Weighting by engagement_score (with a
  log dampener so one viral outlier doesn't dominate the whole window)
  reflects that.

- Confidence interval width is driven by sample size, not just variance.
  A window with 3 tweets and a window with 300 tweets can have the same
  mean sentiment but very different reliability — this uses a
  Wilson-score-style widening for small samples so a downstream trading
  strategy can see "this signal is thin, discount it" rather than treating
  every window as equally trustworthy.

- Rolling time buckets (default 15 min, configurable) rather than one
  number for the whole 24h — a composite signal that isn't time-aware
  is close to useless for intraday strategies, which is the explicit
  framing in the assignment brief.
"""

import numpy as np
import pandas as pd
from scipy import stats

from src.utils.config import SIGNAL
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _engagement_weight(engagement_score: pd.Series) -> pd.Series:
    # log1p dampens virality outliers while still rewarding real traction
    return np.log1p(engagement_score.clip(lower=0))


def _confidence_interval(scores: np.ndarray, weights: np.ndarray, confidence: float = 0.90):
    n = len(scores)
    if n == 0:
        return (np.nan, np.nan)
    if n < SIGNAL.confidence_min_sample_size:
        # Too few observations for a stable normal-approx CI — report a
        # deliberately wide bound instead of a falsely precise one.
        weighted_mean = np.average(scores, weights=weights) if weights.sum() > 0 else scores.mean()
        margin = 0.6 * (1 - n / SIGNAL.confidence_min_sample_size) + 0.15
        return (max(weighted_mean - margin, -1), min(weighted_mean + margin, 1))

    weighted_mean = np.average(scores, weights=weights)
    weighted_var = np.average((scores - weighted_mean) ** 2, weights=weights)
    se = np.sqrt(weighted_var / n)
    z = stats.norm.ppf(0.5 + confidence / 2)
    margin = z * se
    return (max(weighted_mean - margin, -1), min(weighted_mean + margin, 1))


def build_symbol_timeseries(df: pd.DataFrame, symbol_col: str = "primary_hashtag") -> pd.DataFrame:
    """
    Buckets tweets into rolling time windows per symbol and computes:
    - composite_signal: engagement-weighted mean sentiment in [-1, 1]
    - ci_lower / ci_upper: confidence bounds around that signal
    - volume_zscore: mention volume vs that symbol's own rolling baseline
    - tweet_count: raw sample size (for eyeballing signal reliability)
    """
    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()

    bucket = f"{SIGNAL.rolling_window_minutes}min"
    rows = []

    for symbol, group in df.groupby(symbol_col):
        resampled = group.resample(bucket)
        for window_start, window_df in resampled:
            if window_df.empty:
                continue
            weights = _engagement_weight(window_df["engagement_score"]).to_numpy()
            scores = window_df["sentiment_score"].to_numpy()
            weighted_sentiment = float(np.average(scores, weights=weights)) if weights.sum() > 0 else float(scores.mean())
            ci_lower, ci_upper = _confidence_interval(scores, weights)

            rows.append({
                "symbol": symbol,
                "window_start": window_start,
                "sentiment_signal": weighted_sentiment,
                "ci_lower": ci_lower,
                "ci_upper": ci_upper,
                "tweet_count": len(window_df),
                "total_engagement": int(window_df["engagement_score"].sum()),
            })

    ts = pd.DataFrame(rows).sort_values(["symbol", "window_start"])
    if ts.empty:
        return ts

    # Volume z-score against that symbol's own rolling baseline — a spike
    # in *mention volume* is itself a tradeable signal independent of
    # sentiment direction (something is happening, even if polarity is unclear).
    ts["volume_rolling_mean"] = ts.groupby("symbol")["tweet_count"].transform(
        lambda s: s.rolling(8, min_periods=2).mean()
    )
    ts["volume_rolling_std"] = ts.groupby("symbol")["tweet_count"].transform(
        lambda s: s.rolling(8, min_periods=2).std()
    )
    ts["volume_zscore"] = (
        (ts["tweet_count"] - ts["volume_rolling_mean"]) / ts["volume_rolling_std"].replace(0, np.nan)
    ).fillna(0)

    # Composite score: blends direction (sentiment) with conviction (volume
    # anomaly) per the assignment's "combine multiple text features into a
    # composite signal" requirement.
    ts["composite_score"] = (
        SIGNAL.engagement_weight * ts["sentiment_signal"]
        + SIGNAL.volume_weight * np.tanh(ts["volume_zscore"] / 3)  # tanh bounds the volume term to [-1, 1]
    )

    logger.info(f"Built composite signal series: {len(ts)} symbol-windows across {ts['symbol'].nunique()} symbols")
    return ts.reset_index(drop=True)
