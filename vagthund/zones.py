"""Grøn, gul og rød zone.

Reglen, der beskytter vagthunden selv: zonen kan kun gå OP.
Når flere tjek giver hver sin zone, vinder den strengeste.
"""

GREEN = "green"
YELLOW = "yellow"
RED = "red"

_ORDER = {GREEN: 0, YELLOW: 1, RED: 2}


def max_zone(*zones: str) -> str:
    """Returnér den strengeste zone. Ukendte værdier tælles som gul (aldrig grøn)."""
    result = GREEN
    for z in zones:
        if z is None:
            continue
        z = z if z in _ORDER else YELLOW
        if _ORDER[z] > _ORDER[result]:
            result = z
    return result


class CheckResult:
    """Resultatet af ét tjek: en zone og en liste af begrundelser på dansk."""

    def __init__(self, zone: str = GREEN, reasons=None):
        self.zone = zone
        self.reasons = list(reasons or [])

    def add(self, zone: str, reason: str):
        self.zone = max_zone(self.zone, zone)
        self.reasons.append(reason)

    def merge(self, other: "CheckResult"):
        self.zone = max_zone(self.zone, other.zone)
        self.reasons.extend(other.reasons)

    def to_dict(self):
        return {"zone": self.zone, "reasons": self.reasons}
