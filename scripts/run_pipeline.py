"""
End-to-end pipeline: load raw parquet -> clean -> dedup -> sentiment
features -> composite signals -> plots + processed parquet output.

Usage:
    python scripts/generate_sample_data.py   # or run the real scraper first
    python scripts/run_pipeline.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.storage.parquet_store import ParquetStore
from src.storage.dedup import deduplicate
from src.processing.cleaner import clean_dataframe
from src.signals.text_features import TextFeaturizer, add_sentiment_features
from src.signals.signal_generator import build_symbol_timeseries
from src.visualization.streaming_plots import (
    plot_sentiment_scatter_sampled, plot_composite_signal, plot_top_terms,
)
from scripts.generate_evaluation_report import build_per_hashtag_report, render_markdown
from src.utils.config import DATA_PROCESSED, DATA_SAMPLE
from src.utils.logger import get_logger

logger = get_logger(__name__, log_file="pipeline.log")


def main():
    logger.info("=== Pipeline start ===")

    store = ParquetStore()
    raw_df = store.load()
    if raw_df.empty:
        logger.error("No raw data found. Run scripts/generate_sample_data.py "
                      "or the scraper (src/scraper/twitter_scraper.py) first.")
        return
    logger.info(f"Loaded {len(raw_df)} raw tweets.")

    deduped = deduplicate(raw_df, near_duplicates=True)

    cleaned = clean_dataframe(deduped)
    logger.info(f"Cleaned dataset: {len(cleaned)} tweets remain.")

    featurizer = TextFeaturizer()
    tfidf_matrix = featurizer.fit_transform(cleaned["content_clean"])
    top_terms = featurizer.top_terms(tfidf_matrix, n=15)

    scored = add_sentiment_features(cleaned)

    signal_ts = build_symbol_timeseries(scored)

    # Persist processed outputs
    processed_path = DATA_PROCESSED / "tweets_scored.parquet"
    scored.drop(columns=["emojis"]).to_parquet(processed_path, index=False)  # list-of-str col; drop for portability
    logger.info(f"Wrote scored dataset to {processed_path}")

    if not signal_ts.empty:
        signal_path = DATA_PROCESSED / "composite_signals.parquet"
        signal_ts.to_parquet(signal_path, index=False)
        logger.info(f"Wrote composite signal series to {signal_path}")

    # Plots -> data/sample so they ship with the repo for reviewers
    plot_sentiment_scatter_sampled(scored, DATA_SAMPLE / "sentiment_scatter.png")
    if not signal_ts.empty:
        plot_composite_signal(signal_ts, DATA_SAMPLE / "composite_signal.png")
    plot_top_terms(top_terms, DATA_SAMPLE / "top_terms.png")

    # Per-hashtag evaluation — target vs. actual, sentiment/engagement shape
    # per tag. This is the client's explicit "evaluate the collected data"
    # ask, so it runs as part of the standard pipeline, not as an afterthought.
    eval_report = build_per_hashtag_report(raw_df, scored)
    eval_report.to_csv(DATA_PROCESSED / "per_hashtag_evaluation.csv", index=False)
    eval_md = render_markdown(eval_report)
    (DATA_PROCESSED / "per_hashtag_evaluation.md").write_text(eval_md, encoding="utf-8")
    logger.info("Wrote per-hashtag evaluation report.")

    _print_summary(scored, signal_ts, top_terms)
    print(eval_md)
    logger.info("=== Pipeline complete ===")


def _print_summary(scored, signal_ts, top_terms):
    print("\n" + "=" * 60)
    print("PIPELINE SUMMARY")
    print("=" * 60)
    print(f"Tweets after clean+dedup: {len(scored)}")
    print(f"Sentiment split: {scored['sentiment_label'].value_counts().to_dict()}")
    print(f"Script mix: {scored['script'].value_counts().to_dict()}")
    if not signal_ts.empty:
        latest = signal_ts.sort_values('window_start').groupby('symbol').tail(1)
        print("\nLatest composite signal per symbol:")
        for _, row in latest.iterrows():
            print(f"  {row['symbol']:<18} score={row['composite_score']:+.3f}  "
                  f"(CI [{row['ci_lower']:+.2f}, {row['ci_upper']:+.2f}], n={row['tweet_count']})")
    print(f"\nTop terms: {', '.join(t for t, _ in top_terms[:10])}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
