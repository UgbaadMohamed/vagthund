"""Lag 3: Stop forbudte handlinger.

Når AI'en vil bruge et værktøj (et "tool call"), tjekkes det mod
virksomhedens rettighedskort i config.yaml:
  tilladt              -> grøn
  kraever_godkendelse  -> gul (sættes på godkendelseslisten)
  forbudt              -> rød
Ukendte værktøjer er ALTID forbudte.
"""

import json

from vagthund.zones import GREEN, RED, YELLOW, CheckResult


def _parse_args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def check_action(name: str, raw_args, config: dict) -> CheckResult:
    result = CheckResult()
    rights = config.get("rettigheder", {}) or {}
    rule = rights.get(name)

    if rule is None:
        result.add(RED, f"Ukendt handling '{name}' er ikke på rettighedskortet")
        return result

    if isinstance(rule, str):
        rule = {"regel": rule}
    base = rule.get("regel", "forbudt")
    args = _parse_args(raw_args)

    if base == "forbudt":
        result.add(RED, f"Handlingen '{name}' er forbudt")
        return result
    if base == "kraever_godkendelse":
        result.add(YELLOW, f"Handlingen '{name}' kræver godkendelse af et menneske")
        return result
    if base != "tilladt":
        result.add(RED, f"Ukendt regel '{base}' for '{name}' (behandles som forbudt)")
        return result

    # Ekstra betingelser for tilladte handlinger
    limit = rule.get("kraever_godkendelse_over")
    field = rule.get("felt")
    if limit is not None and field:
        try:
            value = float(args.get(field, 0))
        except (TypeError, ValueError):
            result.add(YELLOW, f"'{name}': feltet '{field}' kunne ikke læses")
            return result
        if value > float(limit):
            result.add(YELLOW, f"'{name}' med {field}={value:g} er over grænsen på {limit}")

    allowed_domains = rule.get("kun_domaener")
    mail_field = rule.get("mail_felt")
    if allowed_domains and mail_field:
        address = str(args.get(mail_field, "")).lower()
        domain = address.rsplit("@", 1)[-1] if "@" in address else ""
        if domain not in [d.lower() for d in allowed_domains]:
            result.add(YELLOW, f"'{name}' til en modtager uden for de godkendte domæner")

    if not result.reasons:
        result.zone = GREEN
    return result
