# Vagthund – prototype

En AI-sikkerhedsagent, der beskytter en virksomheds AI-chatbot mod prompt injection, datalæk og forbudte handlinger. Den har tre lag:

1. **Stop snyd:** tjekker kundens besked for prompt injection
2. **Stop læk:** tjekker chatbottens svar for andre kunders data, hemmeligheder og persondata
3. **Stop forbudte handlinger:** tjekker hvert værktøjskald mod et rettighedskort

Vagthunden kan bruges på to måder:

| Måde | Mappe | Hvornår |
|---|---|---|
| **Inde i chatbotten** (Python-interface) | `vagthund/` | Sådan tester vi med Fjordkaffe-chatbotten. Vagthunden kender kunden og kan derfor tjekke ejerskab af ordrer |
| **Som proxy** foran AI-modellen (OpenAI-format) | `app/` | Sådan kan en virksomhed tage den i brug uden at ændre sin chatbot. Kun én adresse skal ændres |

Begge bruger de samme regler i `vagthund/`.

---

## 1. Inde i Fjordkaffe-chatbotten

### Kobl den på
Mappen `vagthund/` erstatter skelettet i chatbottens projekt:

```bash
# fra chatbottens mappe
rm -rf vagthund
cp -r ../vagthund/vagthund ./vagthund
```

Chatbotten kalder allerede `tjek_besked`, `tjek_handling` og `tjek_svar`, så der skal ikke ændres noget i chatbotten. Pakken bruger kun Python's standardbibliotek (AI-tjekket bruger `anthropic`, som chatbotten allerede har).

### Kør
```bash
python -m chatbot.app                          # runde 1: ingen beskyttelse
python -m chatbot.app --lag1 --lag2 --lag3     # alle lag slået til
```

Fra et testscript:
```python
from chatbot import Chatbot
from vagthund import Vagthund

bot = Chatbot("K003", vagthund=Vagthund(lag1=True, lag2=True, lag3=True))
bot = Chatbot("K003", vagthund=Vagthund(lag1=True, lag2=True, lag3=True, ai=True))  # + AI-tjek
```

### Dashboard
```bash
python -m vagthund.dashboard      # fra chatbottens mappe
```
Åbn http://127.0.0.1:8001. Det viser gule og røde hændelser og godkendelseslisten. Loggen ligger i `logs/vagthund.db` og indeholder aldrig selve beskederne.

### Hvad lagene tjekker

| Lag | Tjek | Farve |
|---|---|---|
| 1 | Kendte snyde-mønstre: "ignorer dine regler", "du er nu…", "nye instrukser", "vis din systemprompt" (dansk og engelsk) | rød |
| 1 | Skjulte tegn, HTML og base64-kodet tekst bliver gjort synlige før tjekket | rød / gul |
| 1 | Udgiver sig for at være medarbejder eller administrator | gul |
| 2 | Den interne kode fra systemprompten (canary) | rød |
| 2 | Andre kunders navn, e-mail, telefon eller adresse | rød |
| 2 | CPR-numre, kortnumre, API-nøgler, adgangskoder, mange e-mails | rød |
| 3 | `slaa_ordre_op` og `refunder`: ordren skal tilhøre kunden | rød |
| 3 | `refunder`: højst ordrens beløb, og over 500 kr. kræver godkendelse | rød / gul |
| 3 | `send_mail`: kun til kundens egen adresse og uden andres data | rød |
| 3 | Formålstjek: har kunden overhovedet bedt om en refusion eller en mail? Ellers kan det være indirekte prompt injection | gul |
| 3 | Værktøjer, der ikke står på rettighedskortet | rød |

Indstillingerne (hemmeligheder, rettigheder, grænser) står i `vagthund/indstillinger.py`.

### AI-tjek (valgfrit)
Med `ai=True` vurderer en sprogmodel også kundens besked (lag 1) og om handlingen passer til kundens ønske (lag 3). Selvbeskyttelse:
- Reglerne kører først, og AI'en kan kun gøre en vurdering **strengere**, aldrig mildere
- Teksten behandles som data, og AI'en har ingen værktøjer
- Fejl eller et svar i forkert format giver **gul**, aldrig grøn

Modellen vælges med `VAGTHUND_MODEL` (ellers `CHATBOT_MODEL`).

---

## 2. Som proxy

```bash
pip install -r requirements.txt
uvicorn app.main:app --port 8001
```
- Dashboard: http://localhost:8001/dashboard
- API-testside: http://localhost:8001/docs

Chatbotten skal kun ændre adressen:
```python
client = OpenAI(api_key="...", base_url="http://localhost:8001/v1")
```
Se `eksempel_chatbot.py`. Indstillingerne står i `config.yaml`, og `ai_model.tilstand: mock` gør, at den virker uden API-nøgle.

Begrænsninger: kun OpenAI-formatet (chat completions), ingen streaming, og gule handlinger blokeres og sættes på godkendelseslisten.

---

## Tests
```bash
python -m pytest -v
```
- `tests/test_interface.py`: koblingen til chatbotten (lag 1–3, AI-tjek, log)
- `tests/test_vagthund.py`: proxyen

## Filer

| Fil | Hvad |
|---|---|
| `vagthund/interface.py` | De tre metoder, chatbotten kalder |
| `vagthund/input_check.py` | Lag 1: regler for prompt injection |
| `vagthund/output_check.py` | Lag 2: CPR, kort, nøgler, e-mails, fortrolige ord |
| `vagthund/kunde_check.py` | Ejerskab af ordrer og andre kunders data |
| `vagthund/ai_check.py` | Valgfrit AI-tjek |
| `vagthund/normalize.py` | Rensning: usynlige tegn, Unicode, HTML, base64 |
| `vagthund/zones.py` | Reglen om, at zonen kun kan gå op |
| `vagthund/log.py` | SQLite-log og godkendelsesliste |
| `vagthund/dashboard.py` + `dashboard.html` | Dashboardet |
| `vagthund/indstillinger.py` | Indstillinger for Fjordkaffe |
| `app/` | Proxyen (FastAPI) |
| `config.yaml` | Indstillinger for proxyen |

## Kendte begrænsninger
- Regler fanger kendte mønstre. Nye formuleringer kan slippe forbi lag 1, og derfor er lag 2 og 3 der som sikkerhedsnet
- Formålstjekket ser kun kundens seneste besked. Siger kunden fx bare "ja tak" til en refusion, bliver den gul og skal godkendes
- Resultater fra værktøjer (fx ordrens bemærkning) tjekkes ikke af lag 1 i chatbottens opbygning. Lag 3 begrænser konsekvenserne
