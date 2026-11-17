"""Grænsefladen mellem chatbotten og vagthunden.

Chatbotten kalder vagthunden tre steder:

    tjek_besked()    før chatbotten læser kundens besked      (lag 1: stop snyd)
    tjek_handling()  før et værktøj bliver udført             (lag 3: stop forbudte handlinger)
    tjek_svar()      før kunden ser chatbottens svar          (lag 2: stop læk)

Hver metode returnerer en Vurdering med en farve:

    grøn  = ok, fortsæt
    gul   = et menneske skal kigge på det først
    rød   = blokeret

Selvbeskyttelse:
  - reglerne kører altid først, og et valgfrit AI-tjek kan kun gøre vurderingen
    strengere, aldrig mildere
  - fejl i et tjek giver aldrig grøn
  - vagthunden udfører ingen handlinger selv, den svarer kun med en farve

Brug:
    Vagthund()                                 alle lag slået fra (testrunde 1)
    Vagthund(lag1=True, lag2=True, lag3=True)  alle lag med regler
    Vagthund(lag1=True, lag2=True, lag3=True, ai=True)   + AI-tjek (kræver API-nøgle)
"""

from dataclasses import dataclass

from .input_check import check_input
from .indstillinger import FJORDKAFFE
from .kunde_check import Kundedata, andre_kunders_data
from .log import EventLog
from .normalize import normalize
from .output_check import check_output
from .zones import GREEN, RED, YELLOW

GROEN, GUL, ROED = "grøn", "gul", "rød"

_TIL_DANSK = {GREEN: GROEN, YELLOW: GUL, RED: ROED}
_TIL_ENGELSK = {GROEN: GREEN, GUL: YELLOW, ROED: RED}
_STYRKE = {GROEN: 0, GUL: 1, ROED: 2}


def strengeste(*farver):
    """Den strengeste farve vinder. Ukendte værdier tælles som gul (aldrig grøn)."""
    resultat = GROEN
    for f in farver:
        if f is None:
            continue
        f = f if f in _STYRKE else GUL
        if _STYRKE[f] > _STYRKE[resultat]:
            resultat = f
    return resultat


@dataclass
class Vurdering:
    farve: str          # "grøn", "gul" eller "rød"
    begrundelse: str    # kort forklaring, vises i loggen og på dashboardet
    lag: int            # 1, 2 eller 3


class _Fund:
    """Samler farver og begrundelser fra flere tjek."""

    def __init__(self):
        self.farve = GROEN
        self.grunde = []

    def tilfoej(self, farve, grund):
        self.farve = strengeste(self.farve, farve)
        self.grunde.append(grund)

    def vurdering(self, lag, ok_tekst):
        if self.farve == GROEN:
            return Vurdering(GROEN, ok_tekst, lag)
        return Vurdering(self.farve, "; ".join(self.grunde), lag)


class Vagthund:
    def __init__(self, lag1=False, lag2=False, lag3=False, ai=False,
                 indstillinger=None, kundedata=None, ai_dommer=None, log=True):
        # Hvert lag kan slås til og fra, så testrunderne kan køres hver for sig.
        self.lag1 = lag1
        self.lag2 = lag2
        self.lag3 = lag3
        self.ai = ai
        self.cfg = indstillinger or FJORDKAFFE
        self._kundedata = kundedata
        self._ai_dommer = ai_dommer
        self._log_til = log
        self._log = None

    # ------------------------------------------------------------------ hjælpere

    @property
    def kundedata(self):
        if self._kundedata is None:
            self._kundedata = Kundedata(self.cfg.get("data_mappe"))
        return self._kundedata

    @property
    def ai_dommer(self):
        if self._ai_dommer is None:
            from .ai_check import AIDommer
            self._ai_dommer = AIDommer()
        return self._ai_dommer

    def _logger(self, vurdering, handling, vaerktoej=None):
        """Gemmer gule og røde vurderinger til dashboardet. Fejl i loggen må aldrig
        ændre vurderingen, så de ignoreres."""
        if not self._log_til or vurdering.farve == GROEN:
            return
        try:
            if self._log is None:
                sti = self._log_til if isinstance(self._log_til, str) else self.cfg.get("log_fil", "logs/vagthund.db")
                from pathlib import Path
                Path(sti).parent.mkdir(parents=True, exist_ok=True)
                self._log = EventLog(sti)
            grunde = [g.strip() for g in vurdering.begrundelse.split(";") if g.strip()]
            self._log.event(f"lag {vurdering.lag}", _TIL_ENGELSK[vurdering.farve], handling, grunde)
            if vaerktoej and vurdering.farve == GUL:
                self._log.add_approval(vaerktoej, grunde)
        except Exception:
            pass

    # ------------------------------------------------------------------ lag 1

    def tjek_besked(self, besked, kunde):
        """Lag 1: Er kundens besked et forsøg på prompt injection?"""
        if not self.lag1:
            return Vurdering(GROEN, "Lag 1 er slået fra.", 1)
        fund = _Fund()
        try:
            r = check_input(besked, "kundens besked")
            for grund in r.reasons:
                fund.tilfoej(_TIL_DANSK[r.zone], grund)
            if self.ai and fund.farve != ROED:
                farve, grund = self.ai_dommer.vurder_besked(besked)
                if farve != GROEN:
                    fund.tilfoej(farve, grund)
        except Exception as fejl:
            fund.tilfoej(ROED, f"Fejl i lag 1 ({type(fejl).__name__})")
        v = fund.vurdering(1, "Ingen tegn på prompt injection.")
        self._logger(v, "blokeret" if v.farve == ROED else "sendt til en medarbejder")
        return v

    # ------------------------------------------------------------------ lag 2

    def tjek_svar(self, svar, kunde):
        """Lag 2: Indeholder chatbottens svar data, kunden ikke må se?"""
        if not self.lag2:
            return Vurdering(GROEN, "Lag 2 er slået fra.", 2)
        fund = _Fund()
        try:
            ren = normalize(svar or "").lower()
            for hemmelighed in self.cfg.get("hemmeligheder", []):
                if hemmelighed and hemmelighed.lower() in ren:
                    fund.tilfoej(ROED, "En hemmelighed fra systemprompten står i svaret")

            r = check_output(svar or "", {"foelsomme_ord": self.cfg.get("foelsomme_ord", []),
                                          "max_emails_i_svar": 2})
            for grund in r.reasons:
                fund.tilfoej(_TIL_DANSK[r.zone], grund)

            for f in andre_kunders_data(svar, kunde, self.kundedata):
                fund.tilfoej(ROED, f"Andre kunders oplysninger i svaret ({f})")
        except Exception as fejl:
            fund.tilfoej(ROED, f"Fejl i lag 2 ({type(fejl).__name__})")
        v = fund.vurdering(2, "Intet læk fundet.")
        self._logger(v, "svar erstattet" if v.farve == ROED else "svar sendt til en medarbejder")
        return v

    # ------------------------------------------------------------------ lag 3

    def tjek_handling(self, kundens_besked, vaerktoej, input_data, kunde):
        """Lag 3: Må chatbotten udføre denne handling?

        Metoden får kundens oprindelige besked, værktøjets navn og input samt
        kunden. Den får IKKE resten af samtalen eller de data, chatbotten har
        læst. Så kan skjult tekst i data ikke nå herind.
        """
        if not self.lag3:
            return Vurdering(GROEN, "Lag 3 er slået fra.", 3)
        fund = _Fund()
        try:
            self._tjek_rettighed(fund, kundens_besked or "", vaerktoej, input_data or {}, kunde)
            if self.ai and fund.farve == GROEN:
                farve, grund = self.ai_dommer.vurder_handling(kundens_besked, vaerktoej, input_data)
                if farve != GROEN:
                    fund.tilfoej(farve, grund)
        except Exception as fejl:
            fund.tilfoej(ROED, f"Fejl i lag 3 ({type(fejl).__name__})")
        v = fund.vurdering(3, f"'{vaerktoej}' er tilladt.")
        self._logger(v, "blokeret" if v.farve == ROED else "sendt til godkendelse",
                     vaerktoej=vaerktoej)
        return v

    def _tjek_rettighed(self, fund, besked, vaerktoej, data, kunde):
        regel = self.cfg.get("rettigheder", {}).get(vaerktoej)
        if regel is None:
            fund.tilfoej(ROED, f"Ukendt handling '{vaerktoej}' er ikke på rettighedskortet")
            return
        if regel == "forbudt":
            fund.tilfoej(ROED, f"Handlingen '{vaerktoej}' er forbudt")
            return
        if regel == "egen_ordre":
            self._tjek_egen_ordre(fund, vaerktoej, data, kunde)
        elif regel == "kun_egen_mail":
            self._tjek_mail(fund, data, kunde)
        elif regel != "tilladt":
            fund.tilfoej(ROED, f"Ukendt regel '{regel}' for '{vaerktoej}'")
            return

        # Formålstjek: har kunden overhovedet bedt om det her?
        ord_ = self.cfg.get("formaal_ord", {}).get(vaerktoej)
        if ord_ and fund.farve != ROED and not any(o in besked.lower() for o in ord_):
            fund.tilfoej(GUL, f"Kunden har ikke bedt om '{vaerktoej}' (mulig indirekte prompt injection)")

    def _tjek_egen_ordre(self, fund, vaerktoej, data, kunde):
        if not self.kundedata.tilgaengelig:
            fund.tilfoej(GUL, "Vagthunden kan ikke slå ordrer op og kan derfor ikke tjekke ejerskab")
            return
        nummer = data.get("ordrenummer")
        ordre = self.kundedata.ordre(nummer)
        if ordre is None:
            return  # ordren findes ikke; værktøjet svarer selv med en fejl
        if ordre.get("kunde_id") != kunde.get("kunde_id"):
            fund.tilfoej(ROED, f"Ordre {nummer} tilhører en anden kunde")
            return
        if vaerktoej == "refunder":
            try:
                beloeb = float(data.get("beloeb"))
            except (TypeError, ValueError):
                fund.tilfoej(ROED, "Refusionsbeløbet kan ikke læses")
                return
            if beloeb > float(ordre.get("beloeb", 0)):
                fund.tilfoej(ROED, f"Refusion på {beloeb:g} kr. er mere end ordrens beløb ({ordre.get('beloeb')} kr.)")
            elif beloeb > float(self.cfg.get("refusion_godkendelse_over", 500)):
                fund.tilfoej(GUL, f"Refusion på {beloeb:g} kr. er over grænsen og skal godkendes")

    def _tjek_mail(self, fund, data, kunde):
        til = str(data.get("til", "")).strip().lower()
        egen = str(kunde.get("email", "")).strip().lower()
        if not til or til != egen:
            fund.tilfoej(ROED, "Mail til en anden adresse end kundens egen")
            return
        indhold = f"{data.get('emne', '')}\n{data.get('tekst', '')}"
        for f in andre_kunders_data(indhold, kunde, self.kundedata):
            fund.tilfoej(ROED, f"Mailen indeholder andre kunders oplysninger ({f})")
        r = check_output(indhold, {"foelsomme_ord": self.cfg.get("foelsomme_ord", []),
                                   "max_emails_i_svar": 2})
        for grund in r.reasons:
            fund.tilfoej(_TIL_DANSK[r.zone], "I mailen: " + grund.replace(" i svaret", ""))
        for hemmelighed in self.cfg.get("hemmeligheder", []):
            if hemmelighed and hemmelighed.lower() in indhold.lower():
                fund.tilfoej(ROED, "Mailen indeholder en hemmelighed fra systemprompten")
