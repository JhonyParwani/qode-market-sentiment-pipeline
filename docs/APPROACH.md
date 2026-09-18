# Approach

## How I read the assignment

The brief frames this as "convert Twitter chatter into trading signals," which
means the hard part isn't scraping — it's making sure what comes out the other
end is something a trading strategy could actually use without being misled.
That shaped most of the decisions below: I optimized for signal honesty
(confidence intervals that widen when data is thin, a sentiment lexicon tuned
to trading slang instead of a generic one) over raw feature sophistication.

## Data collection

**Selenium against the public search UI**, not the Twitter API — required by
the brief. The scraper (`src/scraper/twitter_scraper.py`) drives a real
browser: search by hashtag/cashtag, scroll, parse the DOM for each tweet card.

Anti-bot handling (`src/scraper/rate_limiter.py`) has three layers:
1. Randomized pacing instead of fixed sleeps — fixed intervals are one of the
   easiest bot fingerprints.
2. A forced cooldown every N scrolls regardless of whether anything looks
   wrong yet.
3. Exponential backoff triggered by detected soft-block signals (rate-limit
   toasts, CAPTCHA elements, login walls), giving up after 5 consecutive
   failures rather than looping against a wall forever.

Cookie-based auth is preferred over username/password specifically because
repeatedly hitting the login flow is itself a bot signal.

**Concurrency** (`src/scraper/concurrent_runner.py`): threads, not
multiprocessing — each scrape session is I/O-bound (waiting on page loads),
not CPU-bound, so threads parallelize the actual bottleneck without fighting
the GIL. Worker count is capped at 3 by default; more concurrent sessions from
one network path raises detection risk faster than it saves time, which is
the wrong trade for a task that needs to run unattended for a while.

## Storage

**Parquet, partitioned by scrape date and hashtag.** Columnar storage means
the analysis layer can read only the columns/partitions it needs instead of
loading everything — this is what actually makes the "scale to 10x data"
requirement realistic rather than aspirational. Writes are batched (~200
tweets) rather than per-row, which amortizes write overhead and bounds data
loss from a mid-session crash to one batch.

**Deduplication is two-tier** (`src/storage/dedup.py`):
- Exact, on `tweet_id` — cheap, catches the same tweet surfaced by two
  overlapping hashtag searches.
- Near-duplicate, via MinHash LSH — catches copy-paste spam and
  near-identical reposts that have distinct tweet IDs. I used MinHash LSH
  instead of pairwise cosine similarity specifically because pairwise
  comparison is O(n²) and stops being usable well before the "10x more data"
  mark; MinHash gets this to roughly O(n).

## Cleaning

Indian market Twitter is heavily code-mixed — Hindi/Hinglish in Latin script,
Devanagari script, and English, sometimes in the same tweet. Two decisions
that matter here (`src/processing/cleaner.py`):
- NFKC Unicode normalization, not just basic encode/decode — handles
  precomposed vs. decomposed characters and combining marks that show up in
  copy-pasted Devanagari text.
- Emoji are extracted into their own column, not discarded. 🚀/📉/🔴/🟢 carry
  real directional signal in market sentiment specifically — throwing them
  away loses information that's essentially free to keep.

## Text-to-signal

Hybrid TF-IDF + a small hand-built finance lexicon
(`src/signals/text_features.py`), rather than one method alone:
- TF-IDF surfaces which terms are driving a window (good for a human glancing
  at "why did sentiment move") but has no notion of polarity on its own.
- Generic sentiment lexicons (VADER, TextBlob) misread trading slang —
  "short" reads negative in general English but is neutral trading
  terminology; "bullish"/"bearish" aren't in general lexicons at all. A small
  domain lexicon fixes exactly the cases that matter here without pulling in
  a heavyweight pretrained model, which also keeps this running with no GPU
  and no external calls — consistent with the "no paid APIs" constraint in
  spirit, not just letter.

**Composite signal** (`src/signals/signal_generator.py`): engagement-weighted
(log-dampened so one viral tweet doesn't dominate a window), bucketed into
15-minute rolling windows per symbol, blended with a volume z-score so a
spike in *mention volume* counts as signal even when polarity is unclear.
Confidence intervals widen explicitly for small sample sizes instead of
reporting a falsely precise number for a window with 3 tweets in it — a
composite signal that doesn't flag its own reliability is worse than no
signal for anything that's actually going to size a position off it.

## Visualization

Memory-efficient by construction, not as an afterthought
(`src/visualization/streaming_plots.py`): reservoir sampling (single-pass,
O(k) memory) for point-cloud plots like the sentiment scatter, and
pre-aggregation (already bucketed by the signal layer) for trend lines —
so plot cost scales with time range, not raw tweet volume.

## What I'd do differently with more time / budget

- Swap the lexicon sentiment scorer for a small fine-tuned transformer
  (FinBERT-style) once there's a labeled sample to validate against — the
  lexicon is defensible and fast but caps out on sarcasm/negation handling.
- Persist a rolling LSH index instead of rebuilding it per pipeline run, so
  dedup works incrementally as new batches land instead of reprocessing the
  whole dataset each time.
- Add a lightweight backtest harness that lags the signal against actual
  NIFTY/BANKNIFTY price data, so "composite score" claims can be checked
  against something instead of just looking plausible.
- Move from threads to a proper job queue (Celery/RQ) if this needs to run
  as a long-lived service rather than a scheduled script.
