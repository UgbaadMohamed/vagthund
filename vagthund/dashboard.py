"""Dashboardet til vagthunden, når den kører inde i chatbotten.

Kræver kun Python (ingen ekstra pakker). Start fra chatbottens mappe:

    python -m vagthund.dashboard

og åbn http://127.0.0.1:8001 i browseren.
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .indstillinger import FJORDKAFFE
from .log import EventLog

HTML = Path(__file__).resolve().parent / "dashboard.html"


def lav_handler(log, virksomhed):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, data, status=200):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/dashboard"):
                body = HTML.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path.startswith("/events"):
                self._json(log.list_events(200))
            elif self.path == "/approvals":
                self._json(log.list_approvals())
            elif self.path == "/health":
                self._json({"status": "ok", "virksomhed": virksomhed, "tilstand": "inde i chatbotten"})
            else:
                self._json({"error": "findes ikke"}, 404)

        def do_POST(self):
            if not self.path.startswith("/approve/"):
                return self._json({"error": "findes ikke"}, 404)
            try:
                sag = int(self.path.rsplit("/", 1)[-1])
                laengde = int(self.headers.get("Content-Length", 0))
                beslutning = json.loads(self.rfile.read(laengde) or b"{}").get("beslutning")
            except (ValueError, json.JSONDecodeError):
                return self._json({"error": "ugyldig forespørgsel"}, 400)
            if beslutning not in ("godkendt", "afvist"):
                return self._json({"error": "beslutning skal være 'godkendt' eller 'afvist'"}, 400)
            if not log.set_approval(sag, beslutning):
                return self._json({"error": "findes ikke eller er allerede behandlet"}, 404)
            log.event("godkendelse", "green", beslutning, [f"Sag #{sag} {beslutning} af et menneske"])
            self._json({"id": sag, "status": beslutning})

        def log_message(self, *args):
            pass  # hold terminalen ren

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Vagthundens dashboard")
    parser.add_argument("--db", default=FJORDKAFFE["log_fil"], help="sti til vagthundens log")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    log = EventLog(args.db)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), lav_handler(log, FJORDKAFFE["virksomhed"]))
    print(f"Dashboard: http://127.0.0.1:{args.port}   (log: {args.db})   Stop med Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
