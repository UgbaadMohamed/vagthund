# Vagthund – prototype

En AI-sikkerhedsagent, der sidder som proxy mellem en virksomheds chatbot og AI-modellen og stopper prompt injection, datalæk og forbudte handlinger.

```
Bruger → Chatbot → VAGTHUND → AI-model
                   1. Stop snyd (input)
                   2. Stop læk (output)
                   3. Stop forbudte handlinger
```

## Kom i gang

```bash
pip install -r requirements.txt
uvicorn app.main:app --port 8001
```

- Dashboard: http://localhost:8001/dashboard
- API-testside (automatisk fra FastAPI): http://localhost:8001/docs

I `config.yaml` står `ai_model.tilstand: mock`, så den virker uden API-nøgle og uden internet.

## Kobl en chatbot på

Chatbotten skal kun ændre adressen:

```python
client = OpenAI(api_key="...", base_url="http://localhost:8001/v1")
```

Se `eksempel_chatbot.py`. Hvert svar har en header `X-Vagthund-Zone` (green, yellow eller red).

### Brug en rigtig AI-model

1. Sæt `ai_model.tilstand: openai` i `config.yaml`
2. Sæt nøglen som miljøvariabel, aldrig i koden: `export OPENAI_API_KEY=sk-...`
3. Genstart vagthunden

## Test uden rigtig AI-model

Mock-modellen kan styres fra beskeden:

| Skriv i beskeden | Mock-AI'en gør |
|---|---|
| `[mock-svar:TEKST]` | svarer præcis TEKST (bruges til at teste lag 2) |
| `[mock-tool:refunder {"belob": 1200}]` | "vil" bruge værktøjet refunder (bruges til at teste lag 3) |
| alt andet | svarer `Mock-svar: <beskeden>` |

## Kør testcases

```bash
python -m pytest -v
```

34 testcases: normale beskeder (falske alarmer), direkte, indirekte og kodet prompt injection, læk i svar, handlinger, angreb på vagthunden selv, overvågningstilstand, log uden indhold og fejlhåndtering.

## Filer

| Fil | Hvad |
|---|---|
| `app/main.py` | Proxyen: binder lagene sammen og håndterer endpoints |
| `app/normalize.py` | Rensning: usynlige tegn, Unicode, HTML, base64 |
| `app/input_check.py` | Lag 1: regler for prompt injection |
| `app/output_check.py` | Lag 2: CPR, kort, nøgler, e-mails, canary, følsomme ord |
| `app/action_check.py` | Lag 3: rettighedskortet |
| `app/zones.py` | Grøn/gul/rød og reglen om, at zonen kun kan gå op |
| `app/log.py` | SQLite-log og godkendelsesliste (gemmer aldrig beskedernes indhold) |
| `app/upstream.py` | Videresendelse til AI-modellen + mock-model |
| `config.yaml` | Indstillinger for én virksomhed |
| `dashboard.html` | Dashboard med hændelser og godkendelser |

## Endpoints

| Endpoint | Bruges af |
|---|---|
| `POST /v1/chat/completions` | Chatbotten (samme format som OpenAI) |
| `GET /events` | Dashboardet: hændelser |
| `GET /approvals` | Dashboardet: godkendelsesliste |
| `POST /approve/{id}` med `{"beslutning": "godkendt"}` eller `"afvist"` | Dashboardet |
| `GET /health` | Tjek om vagthunden kører |

## Tilpas til en ny virksomhed

Kopiér `config.yaml` og ret:
- `rettigheder`: virksomhedens værktøjer. Ukendte værktøjer er altid forbudte
- `foelsomme_ord`: kundenavne, projekter osv.
- `canary`: en unik kode, som også lægges i chatbottens instruktioner
- `tilstand`: start med `overvaag` i de første uger, skift til `bloker` bagefter

Start med en anden konfiguration: `VAGTHUND_CONFIG=firma2.yaml uvicorn app.main:app --port 8001`

## Kendte begrænsninger

- Streaming understøttes ikke (chatbotten skal bruge `stream=false`)
- Gule handlinger blokeres og sættes på godkendelseslisten. Vagthunden udfører dem ikke selv efter godkendelse
- Reglerne fanger kendte mønstre. Nye formuleringer kan slippe forbi lag 1, og derfor er lag 2 og 3 der som sikkerhedsnet
- Kun ét AI-svar-format (OpenAI chat completions) understøttes
