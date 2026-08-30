"""
Memory-efficient plotting for datasets too large to comfortably hold as
matplotlib artists in one pass.

Two techniques, applied depending on what's being plotted:

1. Reservoir sampling for scatter/raw-point plots (e.g. individual tweet
   sentiment over time). Plotting 200k+ points is both slow to render and
   visually useless — points overplot into a solid blob. Reservoir sampling
   gives a uniform random sample of a fixed, memory-bounded size in a
   single O(n) pass over the data, without needing to load the full
   dataset into memory first (works over a chunked/streamed iterator).

2. Pre-aggregation for line/bar plots (the composite signal time series).
   These are already bucketed by signal_generator.py, so no sampling is
   needed — the point count is bounded by (time range / bucket size), not
   by raw tweet volume. This is the preferred path whenever the plot is
   a trend rather than a point cloud.

Both write directly to PNG via Agg backend rather than holding a figure in
an interactive backend, and figures are explicitly closed after saving —
matplotlib silently accumulates open figures otherwise, which is a common
memory leak in long-running analysis scripts.
"""

import random
from pathlib import Path
from typing import Iterator

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from src.utils.logger import get_logger

logger = get_logger(__name__)


def reservoir_sample(row_iterator: Iterator[dict], k: int = 5000, seed: int = 42) -> list[dict]:
    """Classic Algorithm R. Single pass, O(k) memory regardless of stream
    length — this is what makes it safe to run against a dataset far larger
    than fits in RAM."""
    rng = random.Random(seed)
    reservoir = []
    for i, row in enumerate(row_iterator):
        if i < k:
            reservoir.append(row)
        else:
            j = rng.randint(0, i)
            if j < k:
                reservoir[j] = row
    return reservoir


def plot_sentiment_scatter_sampled(df: pd.DataFrame, out_path: Path, sample_size: int = 5000):
    """Scatter of individual tweet sentiment vs time, using a reservoir
    sample when the dataset exceeds sample_size — avoids ever materializing
    a plot with more points than are visually distinguishable anyway."""
    if df.empty:
        logger.warning("No data to plot for sentiment scatter.")
        return

    if len(df) > sample_size:
        sampled = pd.DataFrame(reservoir_sample(df.to_dict("records"), k=sample_size))
        logger.info(f"Reservoir-sampled {len(df)} -> {len(sampled)} points for plotting.")
    else:
        sampled = df

    fig, ax = plt.subplots(figsize=(11, 5))
    colors = sampled["sentiment_score"].map(lambda s: "#2e7d32" if s > 0.2 else ("#c62828" if s < -0.2 else "#9e9e9e"))
    ax.scatter(
        pd.to_datetime(sampled["timestamp"]), sampled["sentiment_score"],
        s=sampled["engagement_score"].clip(upper=200) / 8 + 4,
        c=colors, alpha=0.5, edgecolors="none",
    )
    ax.set_ylim(-1.1, 1.1)
    ax.set_ylabel("Tweet sentiment score")
    ax.set_title(f"Tweet-level sentiment over time (n={len(df)}, {len(sampled)} plotted)")
    ax.axhline(0, color="grey", linewidth=0.8, linestyle="--")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)  # explicit close — see module docstring
    logger.info(f"Saved sentiment scatter to {out_path}")


def plot_composite_signal(ts: pd.DataFrame, out_path: Path, symbol: str = None):
    """Line plot of the pre-aggregated composite signal — no sampling
    needed since signal_generator.py already bucketed this to
    (time_range / window_size) rows."""
    if ts.empty:
        logger.warning("No signal data to plot.")
        return

    fig, ax = plt.subplots(figsize=(11, 5))
    symbols = [symbol] if symbol else ts["symbol"].unique()
    for sym in symbols:
        sub = ts[ts["symbol"] == sym]
        ax.plot(sub["window_start"], sub["composite_score"], label=sym, linewidth=1.6)
        ax.fill_between(sub["window_start"], sub["ci_lower"], sub["ci_upper"], alpha=0.15)

    ax.axhline(0, color="grey", linewidth=0.8, linestyle="--")
    ax.set_ylabel("Composite signal")
    ax.set_title("Composite trading signal with confidence band")
    ax.legend(loc="upper left", fontsize=8)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    logger.info(f"Saved composite signal plot to {out_path}")


def plot_top_terms(top_terms: list[tuple[str, float]], out_path: Path):
    if not top_terms:
        logger.warning("No terms to plot.")
        return
    terms, scores = zip(*top_terms)
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.barh(range(len(terms)), scores, color="#1565c0")
    ax.set_yticks(range(len(terms)))
    ax.set_yticklabels(terms)
    ax.invert_yaxis()
    ax.set_xlabel("TF-IDF weight (summed)")
    ax.set_title("Top terms driving the current window")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    logger.info(f"Saved top-terms plot to {out_path}")
