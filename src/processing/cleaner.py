"""
Cleaning and normalization.

Indian market Twitter is heavily code-mixed — Hindi/Hinglish written in
Latin script ("kal market girega yaar"), Devanagari script, and English
in the same thread, often the same tweet. A cleaner tuned only for English
would silently mangle or drop a meaningful chunk of this dataset, so a few
things here are deliberate:

- NFKC unicode normalization (not just .encode/.decode) — handles the
  precomposed vs decomposed rupee sign, combining marks on Devanagari
  vowel signs, and full-width characters that sometimes show up in
  copy-pasted tweets.
- Emoji are NOT stripped, only isolated into their own column. In market
  sentiment specifically, 🚀/📉/🔴/🟢 carry real directional signal that
  text-only sentiment models miss — throwing them away loses information
  cheaply available for free.
- Devanagari-script tweets are flagged (not translated) — translation
  quality for financial slang is unreliable enough that mistranslating
  and silently blending it into the English-only signal would be worse
  than treating it as a separate language bucket in the signal layer.
"""

import re
import unicodedata

import emoji
import pandas as pd

from src.utils.logger import get_logger

logger = get_logger(__name__)

_URL_RE = re.compile(r"http\S+|www\.\S+")
_HANDLE_RE = re.compile(r"@\w+")
_HASHTAG_RE = re.compile(r"#(\w+)")
_MULTISPACE_RE = re.compile(r"\s+")
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
_CASHTAG_RE = re.compile(r"\$([A-Za-z]{2,10})\b")


def normalize_unicode(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def extract_emojis(text: str) -> list:
    return [c for c in text if c in emoji.EMOJI_DATA]


def detect_script(text: str) -> str:
    if _DEVANAGARI_RE.search(text):
        return "devanagari_mixed" if re.search(r"[a-zA-Z]", text) else "devanagari"
    return "latin"


def clean_content(raw_text: str) -> str:
    text = normalize_unicode(raw_text)
    text = _URL_RE.sub("", text)
    text = emoji.replace_emoji(text, replace="")
    text = _MULTISPACE_RE.sub(" ", text).strip()
    return text


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()
    df["content_raw"] = df["content"]
    df["emojis"] = df["content"].apply(extract_emojis)
    df["script"] = df["content"].apply(detect_script)
    df["cashtags_extra"] = df["content"].apply(lambda t: [m.lower() for m in _CASHTAG_RE.findall(t)])
    df["content_clean"] = df["content"].apply(clean_content)

    before = len(df)
    df = df[df["content_clean"].str.len() >= 3]  # drop empty/emoji-only tweets post-clean
    dropped = before - len(df)
    if dropped:
        logger.info(f"Dropped {dropped} tweets that were empty after cleaning.")

    df["username"] = df["username"].str.strip().str.lower()
    df["hashtags"] = df["hashtags"].apply(lambda hs: sorted(set(h.lower() for h in hs)))

    return df.reset_index(drop=True)
