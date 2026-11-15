# ruff: noqa: RUF001 - the translation table maps look-alike characters on purpose
"""Text normalisation shared by all extractors (docs/05 §3.5).

NFKC folds ligatures (ﬁ → fi) and full-width forms; smart quotes, dashes and bullet glyphs become
ASCII-ish equivalents; words hyphenated across a line break are re-joined; whitespace runs inside
a line collapse. Line breaks are kept: sectioning and claim parsing rely on them.
"""

from __future__ import annotations

import re
import unicodedata

_TRANSLATE = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "‛": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "‐": "-",
        "‑": "-",
        "‒": "-",
        "–": "-",
        "—": "-",
        "―": "-",
        "−": "-",
        "•": "-",
        "●": "-",
        "▪": "-",
        "■": "-",
        "‣": "-",
        "⁃": "-",
        "·": "-",
        "": "-",  # Symbol-font bullet from Word
        "": "-",
        " ": " ",
        "​": "",
        "‌": "",
        "‍": "",
        "﻿": "",
        "­": "",  # soft hyphen
        "\t": " ",
        "\r": "\n",
    }
)

_HYPHEN_WRAP = re.compile(r"([a-z]{2,})-\n([a-z]{2,})")
_SPACES = re.compile(r"[ \f\v]+")
_BLANK_LINES = re.compile(r"\n{3,}")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0e-\x1f\x7f]")


def normalise_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_TRANSLATE)
    text = _CONTROL.sub("", text)
    text = _HYPHEN_WRAP.sub(r"\1\2", text)
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()
