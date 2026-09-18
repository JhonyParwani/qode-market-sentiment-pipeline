# Qode Market Intelligence

A data collection and analysis pipeline that turns X/Twitter chatter around Indian
equity markets (#nifty50, #sensex, #banknifty, #intraday, ...) into a
time-bucketed, confidence-scored trading signal — built for the Qode technical
assignment.

No paid APIs or official Twitter/X API are used anywhere in this repo, per the
assignment constraint. Collection is done via Selenium against the public
search UI.

**Revision note:** updated per client feedback to target 2,000 real tweets
*per* required hashtag (#nifty50, #sensex, #intraday, #banknifty), not 2,000
total. `src/utils/config.py::tweets_per_hashtag` controls this, and
`scripts/generate_evaluation_report.py` produces the per-hashtag breakdown
(target vs. actual, sentiment split, engagement) now included as part of
every pipeline run. See `data/processed/per_hashtag_evaluation.md` after
running the live scraper.

## What this actually does, in one paragraph

A Selenium scraper pulls recent tweets for a set of hashtags/cashtags, writing
them in batches to a partitioned Parquet dataset. A processing stage cleans
and normalizes the text (Unicode-safe, handles Hindi/Hinglish/Devanagari
code-mixing), deduplicates both exact repeats and near-duplicate spam/copy-paste
via MinHash LSH, and scores each tweet with a domain-specific sentiment lexicon
(generic sentiment models misread trading slang — see `docs/APPROACH.md`).
A signal layer aggregates that into an engagement-weighted, time-bucketed
composite score per symbol with a confidence interval that widens honestly
when sample sizes are thin. A visualization layer plots all of it without
ever holding more data in memory than a fixed sample size, so it doesn't fall
over on a dataset 10x this size.

## Repo structure

```
src/
  scraper/          Selenium scraper, rate limiter / anti-bot handling, concurrency, data schema
  storage/           Parquet read/write, exact + near-duplicate dedup
  processing/        Text cleaning, Unicode/script normalization
  signals/           TF-IDF + lexicon sentiment, composite signal + confidence intervals
  visualization/     Memory-efficient (sampled/pre-aggregated) plotting
  utils/             Config, logging
scripts/
  generate_sample_data.py   synthetic demo dataset (see "About the sample data" below)
  run_pipeline.py            end-to-end: load -> clean -> dedup -> score -> signal -> plots
data/
  raw/                partitioned Parquet from the scraper (gitignored — regenerate locally)
  processed/          scored tweets + composite signal Parquet
  sample/             committed sample outputs: preview CSV + 3 plots
docs/
  APPROACH.md         design rationale, tradeoffs, what I'd do with more time
tests/                pytest unit tests for dedup + text/sentiment features
```

## Setup

```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

You'll also need Chrome + a matching chromedriver on PATH for the live scraper
(not needed just to run the pipeline against sample data).

## Running it

**Option A — see it work immediately, no credentials needed:**
```bash
python scripts/generate_sample_data.py   # ~2,400 synthetic tweets, realistic schema/shape
python scripts/run_pipeline.py
```
This is what produced everything under `data/sample/`.

**Option B — run the real scraper:**
```bash
export X_AUTH_TOKEN=...   # see "Auth" below
export X_CT0=...
python -m src.scraper.twitter_scraper       # sequential, one hashtag at a time
# or
python -m src.scraper.concurrent_runner     # parallel across hashtags, 3 workers
python scripts/run_pipeline.py
```

### Auth
Cookie-based auth (`X_AUTH_TOKEN` + `X_CT0`, pulled from an authenticated
browser session's cookies) is preferred over username/password — it doesn't
re-trigger X's login-flow bot detection on every run. Username/password is
supported as a fallback (see `src/scraper/twitter_scraper.py::_login`).

### Tests
```bash
pytest tests/ -v
```

## About the sample data — read this before submitting

`generate_sample_data.py` produces **synthetic** data — realistic schema and
shape (power-law engagement, mixed Hindi/English content, injected
duplicates) so the pipeline mechanics can be demoed without live credentials.
It exists to let a reviewer verify the pipeline works; **it is not a
substitute for the 2,000-real-tweets-per-hashtag requirement**, and
`data/sample/` is labeled and kept separate from `data/raw/` (the real
scrape output) for exactly that reason.

To actually satisfy this requirement, the live scraper
(`src/scraper/twitter_scraper.py`) needs to run against a real, logged-in X
session — see "Running it, Option B" below. X blocks data-center IPs, so
this has to run from a real machine with a real account, not a CI runner or
cloud sandbox. Run it, then run `scripts/run_pipeline.py`, and check
`data/processed/per_hashtag_evaluation.md` for the actual per-hashtag counts
before submitting. If a hashtag falls short of 2,000, that number goes in
the report as-is along with why (see the report's own "Notes on shortfalls"
section) — it isn't padded with synthetic rows to hit the target.

## Sample output

From the synthetic demo run (pipeline mechanics only — see caveat above):
`data/sample/sample_tweets_preview.csv` — top tweets by engagement
`data/sample/composite_signal.png` — composite signal + confidence band per symbol
`data/sample/sentiment_scatter.png` — tweet-level sentiment scatter (reservoir-sampled)
`data/sample/top_terms.png` — TF-IDF top terms for the current window

From a real scrape run, `scripts/run_pipeline.py` additionally writes
`data/processed/per_hashtag_evaluation.csv` / `.md` — actual tweets collected
per required hashtag against the 2,000 target, post-clean/dedup counts, and
the sentiment/engagement breakdown per tag. This is the file that answers
the client's "evaluate the collected data" ask directly.

## Design notes

Every module docstring in this repo explains *why*, not just what — that's
deliberate, since a big part of this assignment is judging engineering
judgment under constraints, not just working code. `docs/APPROACH.md` pulls
the key decisions together in one place along with what I'd change with more
time/budget.
