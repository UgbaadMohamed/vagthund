"""Vagthunden: en OpenAI-kompatibel proxy med tre forsvarslag.

Chatbotten sender sine beskeder hertil i stedet for direkte til AI-modellen:
    client = OpenAI(api_key="...", base_url="http://localhost:8001/v1")

For hver forespørgsel:
  1. Lag 1 tjekker brugerens beskeder og indhold udefra for prompt injection
  2. Forespørgslen sendes videre til AI-modellen
  3. Lag 2 tjekker AI'ens svar for læk
  4. Lag 3 tjekker AI'ens handlinger (tool calls) mod rettighedskortet
  5. Hændelsen logges, og svaret sendes tilbage

Selvbeskyttelse:
  - reglerne kører altid, og den strengeste zone vinder (max_zone)
  - fejl i et tjek blokerer (fail closed), de lader aldrig noget igennem
  - vagthunden har ingen værktøjer: den kan kun sende videre, ændre eller blokere
"""

import os
from pathlib import Path

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from . import upstream
from .action_check import check_action
from .input_check import check_input
from .log import EventLog
from .output_check import check_output
from .zones import GREEN, RED, YELLOW, CheckResult, max_zone

BASE_DIR = Path(__file__).resolve().parent.parent


def load_config(path: str | None = None) -> dict:
    path = path or os.environ.get("VAGTHUND_CONFIG", str(BASE_DIR / "config.yaml"))
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _text_of(content) -> str:
    """Beskeder kan være en streng eller en liste af dele (tekst, billeder osv.)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    return str(content)


def create_app(config: dict | None = None) -> FastAPI:
    cfg = config if config is not None else load_config()
    log = EventLog(cfg.get("log_fil", str(BASE_DIR / "vagthund.db")))
    app = FastAPI(title="Vagthund", version="0.1")

    blocked_msg = cfg.get("standardsvar_blokeret", "Det kan jeg desværre ikke hjælpe med.")
    approval_msg = cfg.get("standardsvar_godkendelse", "Din anmodning er sendt til en medarbejder, som vender tilbage.")

    def blocking() -> bool:
        return cfg.get("tilstand", "bloker") == "bloker"

    def reply(message: dict, model: str, finish: str, zone: str, status: int = 200):
        body = upstream._completion(message, model, finish)
        return JSONResponse(body, status_code=status, headers={"X-Vagthund-Zone": zone})

    @app.get("/health")
    def health():
        return {"status": "ok", "tilstand": cfg.get("tilstand", "bloker"), "virksomhed": cfg.get("virksomhed")}

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        body = await request.json()
        model = body.get("model", "ukendt")
        messages = body.get("messages", [])

        if body.get("stream"):
            return JSONResponse(
                {"error": {"message": "Streaming understøttes ikke af vagthunden i denne prototype. Sæt stream=false.",
                           "type": "invalid_request_error"}},
                status_code=400,
            )

        # ---------- Lag 1: input ----------
        inp = CheckResult()
        try:
            for m in messages:
                role = m.get("role")
                if role == "user":
                    inp.merge(check_input(_text_of(m.get("content")), "bruger"))
                elif role in ("tool", "function"):
                    inp.merge(check_input(_text_of(m.get("content")), "indhold"))
        except Exception as exc:  # fail closed
            inp.add(RED, f"Fejl i input-tjek ({type(exc).__name__})")

        if inp.zone != GREEN:
            stop = inp.zone == RED and blocking()
            log.event("input", inp.zone, "blokeret" if stop else "kun logget", inp.reasons)
            if stop:
                return reply({"role": "assistant", "content": blocked_msg}, model, "stop", RED)

        # ---------- Videre til AI-modellen ----------
        try:
            result = await upstream.forward(body, cfg, request.headers.get("authorization"))
        except Exception as exc:
            log.event("ai_model", YELLOW, "fejl", [f"Kunne ikke kontakte AI-modellen ({type(exc).__name__})"])
            return JSONResponse(
                {"error": {"message": "AI-modellen kunne ikke kontaktes.", "type": "upstream_error"}},
                status_code=502,
            )

        overall = inp.zone
        choices = result.get("choices") or []
        for choice in choices:
            msg = choice.get("message") or {}

            # ---------- Lag 2: output ----------
            out = CheckResult()
            try:
                out = check_output(_text_of(msg.get("content")), cfg)
            except Exception as exc:
                out.add(RED, f"Fejl i output-tjek ({type(exc).__name__})")
            if out.zone != GREEN:
                stop = out.zone == RED and blocking()
                log.event("output", out.zone, "svar erstattet" if stop else "kun logget", out.reasons)
                if stop:
                    msg["content"] = blocked_msg
            overall = max_zone(overall, out.zone)

            # ---------- Lag 3: handlinger ----------
            calls = msg.get("tool_calls") or []
            if calls:
                kept, pending, removed = [], 0, 0
                for call in calls:
                    fn = call.get("function", {}) or {}
                    name = fn.get("name", "?")
                    try:
                        act = check_action(name, fn.get("arguments"), cfg)
                        # Data i selve handlingen kan også lække, fx en mail med CPR-numre
                        leak = check_output(str(fn.get("arguments") or ""), cfg)
                        for why in leak.reasons:
                            act.add(leak.zone, "I handlingen: " + why.replace(" i svaret", ""))
                    except Exception as exc:
                        act = CheckResult(RED, [f"Fejl i handlings-tjek ({type(exc).__name__})"])
                    overall = max_zone(overall, act.zone)

                    if act.zone == GREEN or not blocking():
                        kept.append(call)
                        if act.zone != GREEN:
                            log.event("handling", act.zone, "kun logget", act.reasons)
                    elif act.zone == YELLOW:
                        approval_id = log.add_approval(name, act.reasons)
                        log.event("handling", YELLOW, f"sendt til godkendelse (#{approval_id})", act.reasons)
                        pending += 1
                    else:
                        log.event("handling", RED, "blokeret", act.reasons)
                        removed += 1

                if kept:
                    msg["tool_calls"] = kept
                else:
                    msg.pop("tool_calls", None)
                    msg["content"] = approval_msg if pending and not removed else blocked_msg
                    choice["finish_reason"] = "stop"

            choice["message"] = msg

        return JSONResponse(result, headers={"X-Vagthund-Zone": overall})

    # ---------- Til dashboardet ----------
    @app.get("/events")
    def events(limit: int = 100):
        return log.list_events(limit)

    @app.get("/approvals")
    def approvals():
        return log.list_approvals()

    @app.post("/approve/{approval_id}")
    async def approve(approval_id: int, request: Request):
        data = await request.json()
        decision = data.get("beslutning")
        if decision not in ("godkendt", "afvist"):
            return JSONResponse({"error": "beslutning skal være 'godkendt' eller 'afvist'"}, status_code=400)
        if not log.set_approval(approval_id, decision):
            return JSONResponse({"error": "findes ikke eller er allerede behandlet"}, status_code=404)
        log.event("godkendelse", GREEN, decision, [f"Sag #{approval_id} {decision} af et menneske"])
        return {"id": approval_id, "status": decision}

    @app.get("/dashboard")
    def dashboard():
        return FileResponse(BASE_DIR / "dashboard.html")

    return app


app = None
if os.environ.get("VAGTHUND_NO_AUTOAPP") != "1":
    try:
        app = create_app()
    except FileNotFoundError:
        app = None
