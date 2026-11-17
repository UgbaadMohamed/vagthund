"""Tjek, der kender kunden: hvem ejer ordren, og hvem ejer oplysningerne?

Det er det, der gør vagthunden stærkere end et rent tekstfilter: den ved,
hvilken kunde der er logget ind, og kan derfor se, om chatbotten er ved at
vise eller ændre noget, der tilhører en anden kunde.
"""

import json
import re
from pathlib import Path

from .normalize import normalize


class Kundedata:
    """Læser kunder og ordrer fra JSON-filer, så vagthunden kan slå op i dem."""

    def __init__(self, data_mappe=None):
        self.mappe = self._find_mappe(data_mappe)
        self.kunder = self._laes("kunder.json")
        self.ordrer = self._laes("ordrer.json")

    @staticmethod
    def _find_mappe(data_mappe):
        if data_mappe:
            return Path(data_mappe)
        # Led efter en mappe "data" med ordrer.json: i den mappe, der køres fra,
        # og opad, og derefter ved siden af vagthund-pakken.
        kandidater = [Path.cwd(), *Path.cwd().parents, Path(__file__).resolve().parent.parent]
        for sted in kandidater:
            if (sted / "data" / "ordrer.json").exists():
                return sted / "data"
        return None

    def _laes(self, filnavn):
        if self.mappe is None or not (self.mappe / filnavn).exists():
            return None
        return json.loads((self.mappe / filnavn).read_text(encoding="utf-8"))

    @property
    def tilgaengelig(self):
        return self.ordrer is not None and self.kunder is not None

    def ordre(self, ordrenummer):
        nummer = str(ordrenummer).strip()
        for o in self.ordrer or []:
            if str(o.get("ordrenummer")) == nummer:
                return o
        return None


_TELEFON = re.compile(r"(?<!\d)(?:\d[ \-]?){7}\d(?!\d)")


def _cifre(tekst):
    return re.sub(r"\D", "", str(tekst))


def andre_kunders_data(tekst, kunde, kundedata):
    """Returnerer en liste af fund, hvis teksten indeholder andre kunders oplysninger."""
    if not tekst or kundedata is None or not kundedata.kunder:
        return []
    ren = normalize(tekst).lower()
    telefoner = {_cifre(m) for m in _TELEFON.findall(ren)}
    fund = []
    for anden in kundedata.kunder:
        if anden.get("kunde_id") == kunde.get("kunde_id"):
            continue
        hvad = []
        navn = str(anden.get("navn", "")).lower()
        if navn and re.search(r"\b" + re.escape(navn) + r"\b", ren):
            hvad.append("navn")
        email = str(anden.get("email", "")).lower()
        if email and email in ren:
            hvad.append("e-mail")
        tlf = _cifre(anden.get("telefon", ""))
        if tlf and tlf in telefoner:
            hvad.append("telefon")
        adresse = str(anden.get("adresse", "")).lower()
        if adresse and re.search(r"\b" + re.escape(adresse) + r"\b", ren):
            hvad.append("adresse")
        if hvad:
            fund.append(f"{anden.get('kunde_id')}: {', '.join(hvad)}")
    return fund
