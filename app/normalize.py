"""Rensning af tekst, før den bliver tjekket.

Angribere skjuler ofte instruktioner med usynlige tegn, tegn der ligner
almindelige bogstaver, eller ved at kode teksten (fx base64).
Her gør vi teksten "synlig", så reglerne kan se, hvad der faktisk står.
"""

import base64
import binascii
import re
import unicodedata

# Usynlige tegn: nul-bredde-tegn, retningsskift og Unicode "tag"-tegn
_INVISIBLE = re.compile(
    "[​‌‍⁠﻿­‪-‮⁦-⁩\U000e0000-\U000e007f]"
)
_BASE64_CANDIDATE = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")
_HTML_TAG = re.compile(r"<[^>]+>")


def has_invisible_chars(text: str) -> bool:
    return bool(_INVISIBLE.search(text))


def decode_base64_parts(text: str) -> list[str]:
    """Find stykker, der ligner base64, og returnér dem, der kan læses som tekst."""
    decoded = []
    for match in _BASE64_CANDIDATE.findall(text):
        try:
            raw = base64.b64decode(match, validate=True)
            s = raw.decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
        if sum(ch.isprintable() for ch in s) / max(len(s), 1) > 0.9:
            decoded.append(s)
    return decoded


def normalize(text: str) -> str:
    """Gør teksten klar til tjek: Unicode-normalisering, fjern usynlige tegn og HTML."""
    if not isinstance(text, str):
        text = str(text)
    text = unicodedata.normalize("NFKC", text)  # fx fuld-bredde-bogstaver -> almindelige
    text = _INVISIBLE.sub("", text)
    text = _HTML_TAG.sub(" ", text)  # skjult tekst i HTML-mails bliver synlig
    text = re.sub(r"\s+", " ", text)
    return text.strip()
