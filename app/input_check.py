"""Lag 1: Stop snyd (input).

Tjekker beskeder fra brugeren og indhold, chatbotten har hentet udefra
(fx dokumenter og mails), for prompt injection.
"""

import re

from .normalize import decode_base64_parts, has_invisible_chars, normalize
from .zones import RED, YELLOW, CheckResult

# Regler for kendte snyde-mønstre på dansk og engelsk.
# Hver regel har en forklaring på dansk, som vises på dashboardet.
INJECTION_PATTERNS = [
    (r"\b(ignor[eé]r|glem|tilsides[æa]t)\w*\s+(alle\s+)?(tidligere|dine|ovenst[åa]ende|forrige)\s+(regler|instruktioner|instrukser|beskeder)",
     "Forsøg på at få AI'en til at ignorere sine regler"),
    (r"\b(ignore|disregard|forget)\s+(all\s+)?(previous|prior|above|your|earlier)\s+(instructions|rules|messages|prompts?)",
     "Forsøg på at få AI'en til at ignorere sine regler (engelsk)"),
    (r"\b(du er nu|fra nu af er du|lad som om du er)\b",
     "Forsøg på at give AI'en en ny rolle"),
    (r"\b(you are now|from now on you are|pretend (to be|you are)|act as (an? )?(unrestricted|unfiltered))",
     "Forsøg på at give AI'en en ny rolle (engelsk)"),
    (r"\b(developer mode|udviklertilstand|dan mode|jailbreak|testtilstand|admin(istrator)?[- ]?tilstand)\b",
     "Forsøg på at slå AI'ens begrænsninger fra"),
    (r"\b(vis|afsl[øo]r|gentag|udskriv|print|reveal|show|repeat)\b.{0,30}\b(system ?prompt|dine instruktioner|your instructions|hidden instructions|skjulte instruktioner)",
     "Forsøg på at få AI'en til at afsløre sine instruktioner"),
    (r"\b(til|to|note to|besked til)\s+(the\s+)?((ai|llm)[- ]?)?(ai|llm|assistent(en)?|assistant|agent(en)?|sikkerheds\w*|security \w+|chatbot(ten)?)\s*[:,]",
     "Teksten henvender sig direkte til en AI eller et sikkerhedssystem"),
    (r"\b(mark[ée]r|marker|klassific[ée]r|vurd[ée]r)\b.{0,30}\b(sikker|godkendt|gr[øo]n|harmless|safe)\b",
     "Forsøg på at få en vurdering ændret til sikker"),
    (r"\bmark (this|it)?\s*as (safe|approved|harmless)\b",
     "Forsøg på at få en vurdering ændret til sikker (engelsk)"),
]
_COMPILED = [(re.compile(p, re.IGNORECASE), why) for p, why in INJECTION_PATTERNS]


def _match_rules(text: str, prefix: str = "") -> list[str]:
    return [prefix + why for rx, why in _COMPILED if rx.search(text)]


def check_input(text: str, source: str = "bruger") -> CheckResult:
    """Tjek én tekst. `source` er 'bruger' eller 'indhold' (dokument, mail, værktøjssvar)."""
    result = CheckResult()
    if not text:
        return result

    if has_invisible_chars(text):
        result.add(YELLOW, f"Skjulte tegn fundet i {source}-tekst")

    clean = normalize(text)
    for why in _match_rules(clean):
        result.add(RED, f"{why} ({source})")

    for decoded in decode_base64_parts(clean):
        hits = _match_rules(normalize(decoded), prefix="Kodet tekst (base64): ")
        for why in hits:
            result.add(RED, f"{why} ({source})")

    return result
