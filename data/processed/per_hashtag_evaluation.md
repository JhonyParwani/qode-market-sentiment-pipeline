# Per-Hashtag Evaluation Report

Target: **2000 real tweets per required hashtag** (last 24h). Required tags: nifty50, sensex, intraday, banknifty, stockmarketindia, niftytrading.

**Overall: 3735 / 12500 tweets collected (29.9% of combined target).**

| Hashtag | Target | Collected | % of target | After clean+dedup | Bullish % | Bearish % | Neutral % | Avg engagement |
|---|---|---|---|---|---|---|---|---|
| #NIFTY | 500 | 9 | 1.8% | 9 | 11.1% | 22.2% | 66.7% | 0.0 |
| #banknifty | 2000 | 568 | 28.4% | 361 | 25.8% | 22.2% | 52.1% | 19.9 |
| #intraday | 2000 | 465 | 23.2% | 256 | 32.4% | 23.4% | 44.1% | 27.0 |
| #nifty50 | 2000 | 933 | 46.6% | 680 | 18.8% | 13.1% | 68.1% | 9.5 |
| #niftytrading | 2000 | 409 | 20.4% | 215 | 28.4% | 28.8% | 42.8% | 25.0 |
| #sensex | 2000 | 687 | 34.4% | 482 | 23.9% | 18.3% | 57.9% | 12.6 |
| #stockmarketindia | 2000 | 664 | 33.2% | 354 | 28.8% | 20.6% | 50.6% | 17.8 |

## Notes on shortfalls
- **#NIFTY** reached 9/500 (1.8%). This most often means the tag genuinely doesn't have 500 distinct tweets in a 24h window on live search, or the session hit a soft-block before finishing — check logs/scraper.log for which. Widening `lookback_hours` in src/utils/config.py is the honest fix if the tag is simply low-volume; re-running is the fix if it was rate-limiting.
- **#banknifty** reached 568/2000 (28.4%). This most often means the tag genuinely doesn't have 2000 distinct tweets in a 24h window on live search, or the session hit a soft-block before finishing — check logs/scraper.log for which. Widening `lookback_hours` in src/utils/config.py is the honest fix if the tag is simply low-volume; re-running is the fix if it was rate-limiting.
- **#intraday** reached 465/2000 (23.2%). This most often means the tag genuinely doesn't have 2000 distinct tweets in a 24h window on live search, or the session hit a soft-block before finishing — check logs/scraper.log for which. Widening `lookback_hours` in src/utils/config.py is the honest fix if the tag is simply low-volume; re-running is the fix if it was rate-limiting.
- **#nifty50** reached 933/2000 (46.6%). This most often means the tag genuinely doesn't have 2000 distinct tweets in a 24h window on live search, or the session hit a soft-block before finishing — check logs/scraper.log for which. Widening `lookback_hours` in src/utils/config.py is the honest fix if the tag is simply low-volume; re-running is the fix if it was rate-limiting.
- **#niftytrading** reached 409/2000 (20.4%). This most often means the tag genuinely doesn't have 2000 distinct tweets in a 24h window on live search, or the session hit a soft-block before finishing — check logs/scraper.log for which. Widening `lookback_hours` in src/utils/config.py is the honest fix if the tag is simply low-volume; re-running is the fix if it was rate-limiting.
- **#sensex** reached 687/2000 (34.4%). This most often means the tag genuinely doesn't have 2000 distinct tweets in a 24h window on live search, or the session hit a soft-block before finishing — check logs/scraper.log for which. Widening `lookback_hours` in src/utils/config.py is the honest fix if the tag is simply low-volume; re-running is the fix if it was rate-limiting.
- **#stockmarketindia** reached 664/2000 (33.2%). This most often means the tag genuinely doesn't have 2000 distinct tweets in a 24h window on live search, or the session hit a soft-block before finishing — check logs/scraper.log for which. Widening `lookback_hours` in src/utils/config.py is the honest fix if the tag is simply low-volume; re-running is the fix if it was rate-limiting.