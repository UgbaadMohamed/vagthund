"""Forbindelsen videre til den rigtige AI-model.

To tilstande (sættes i config.yaml under ai_model.tilstand):
  openai -> sender forespørgslen videre til en OpenAI-kompatibel adresse
  mock   -> en falsk AI-model til test uden API-nøgle og uden internet

Mock-modellen kan styres fra testbeskeder:
  [mock-tool:NAVN {"felt": værdi}]  -> AI'en "vil" bruge et værktøj
  [mock-svar:TEKST]                 -> AI'en svarer præcis TEKST
Ellers svarer den bare "Mock-svar: <brugerens sidste besked>".
"""

import json
import os
import re
import time
import uuid

import httpx


def _last_user_text(messages: list) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, list):
                return " ".join(p.get("text", "") for p in c if isinstance(p, dict))
            return c or ""
    return ""


def _completion(message: dict, model: str, finish: str) -> dict:
    return {
        "id": "chatcmpl-" + uuid.uuid4().hex[:12],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
    }


def mock_completion(body: dict) -> dict:
    model = body.get("model", "mock-model")
    text = _last_user_text(body.get("messages", []))

    tool = re.search(r"\[mock-tool:(\w+)\s*(\{.*?\})?\]", text)
    if tool:
        call = {
            "id": "call_" + uuid.uuid4().hex[:8],
            "type": "function",
            "function": {"name": tool.group(1), "arguments": tool.group(2) or "{}"},
        }
        return _completion({"role": "assistant", "content": None, "tool_calls": [call]}, model, "tool_calls")

    fixed = re.search(r"\[mock-svar:(.*?)\]", text, re.DOTALL)
    reply = fixed.group(1) if fixed else f"Mock-svar: {text}"
    return _completion({"role": "assistant", "content": reply}, model, "stop")


async def forward(body: dict, config: dict, auth_header: str | None) -> dict:
    ai = config.get("ai_model", {}) or {}
    if ai.get("tilstand", "mock") == "mock":
        return mock_completion(body)

    url = ai.get("adresse", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
    key_env = ai.get("api_noegle_miljoevariabel", "OPENAI_API_KEY")
    key = os.environ.get(key_env)
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    elif auth_header:
        headers["Authorization"] = auth_header  # brug chatbottens egen nøgle

    timeout = float(ai.get("timeout_sekunder", 30))
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, headers=headers, content=json.dumps(body))
        resp.raise_for_status()
        return resp.json()
