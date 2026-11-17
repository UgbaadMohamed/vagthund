"""Lag 2: Stop læk (output).

Tjekker AI'ens svar for persondata, hemmeligheder, virksomhedens egne
følsomme ord og canary-koden.
"""

import re

from .normalize import normalize
from .zones import RED, YELLOW, CheckResult

_CPR = re.compile(r"\b(0[1-9]|[12]\d|3[01])(0[1-9]|1[0-2])(\d{2})[- ]?(\d{4})\b")
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_SECRETS = [
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), "API-nøgle (OpenAI-format)"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "API-nøgle (AWS)"),
    (re.compile(r"\bghp_[A-Za-z0-9]{36}\b"), "Adgangstoken (GitHub)"),
    (re.compile(r"\bxox[bp]-[A-Za-z0-9-]{10,}"), "Adgangstoken (Slack)"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "Privat nøgle"),
    (re.compile(r"\b(password|adgangskode|kodeord)\s*[:=]\s*\S+", re.IGNORECASE), "Adgangskode"),
]


def _luhn_ok(number: str) -> bool:
    digits = [int(d) for d in number if d.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total, alt = 0, False
    for d in reversed(digits):
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def check_output(text: str, config: dict) -> CheckResult:
    result = CheckResult()
    if not text:
        return result
    clean = normalize(text)

    canary = (config.get("canary") or "").strip()
    if canary and canary.lower() in clean.lower():
        result.add(RED, "Canary-koden står i svaret: AI'en er ved at afsløre sine instruktioner")

    if _CPR.search(clean):
        result.add(RED, "CPR-nummer i svaret")

    if any(_luhn_ok(m) for m in _CARD.findall(clean)):
        result.add(RED, "Betalingskortnummer i svaret")

    for rx, what in _SECRETS:
        if rx.search(clean):
            result.add(RED, f"{what} i svaret")

    emails = set(e.lower() for e in _EMAIL.findall(clean))
    max_emails = int(config.get("max_emails_i_svar", 2))
    if len(emails) > max_emails:
        result.add(RED, f"{len(emails)} e-mailadresser i svaret (mulig kundeliste)")

    for word in config.get("foelsomme_ord", []) or []:
        if word and word.lower() in clean.lower():
            result.add(RED, f"Fortroligt ord i svaret: '{word}'")

    if re.search(r"\b(system ?prompt|mine instruktioner er|my instructions are)\b", clean, re.IGNORECASE):
        result.add(YELLOW, "Svaret ser ud til at tale om AI'ens egne instruktioner")

    return result
