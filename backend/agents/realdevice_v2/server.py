"""
HTTP host server that the Patrol/integration_test on the device calls into
during execution. Uses stdlib http.server only — no extra deps.

Endpoints:
    POST /nav         -> body: {screenshot_b64, current_screen_guess, target_screen}
                         resp: {action, selector, input_text?, ...}
    POST /verify      -> body: {screenshot_b64, expected_screen}
                         resp: {matches_expected, ...}
    POST /hitl        -> body: {kind, question, default?, options?}
                         resp: {answer}
    POST /screenshot  -> body: {name, screenshot_b64}
                         resp: {saved_path}
    POST /done        -> body: {summary}
                         resp: {ok}

The device reaches this server via `adb reverse tcp:<port> tcp:<port>` so
http://localhost:<port> on the device routes to the Mac.
"""
import base64
import json
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from . import hitl
from . import ai_navigator
from . import blank_filter


class HostServer:
    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 5000,
        screenshots_dir: Path,
        app_map: dict,
        documentation: str,
        test_creds: dict[str, str],
        on_hitl: Callable[[str, str, dict], str] | None = None,
    ):
        self.host = host
        self.port = port
        self.screenshots_dir = screenshots_dir
        self.app_map = app_map
        self.documentation = documentation
        self.test_creds = test_creds
        self.on_hitl = on_hitl
        self.events: deque[dict] = deque()
        self.saved_pngs: list[str] = []
        self.flutter_errors: list[dict] = []
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass  # silence default access log

            def _read_json(self) -> dict:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b""
                if not raw:
                    return {}
                return json.loads(raw)

            def _send_json(self, status: int, body: dict) -> None:
                payload = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self):
                if self.path == "/health":
                    self._send_json(200, {"ok": True})
                else:
                    self._send_json(404, {"error": "not found"})

            def do_POST(self):
                try:
                    data = self._read_json()
                except json.JSONDecodeError as e:
                    self._send_json(400, {"error": f"bad json: {e}"})
                    return

                if self.path == "/nav":
                    self._handle_nav(data)
                elif self.path == "/verify":
                    self._handle_verify(data)
                elif self.path == "/hitl":
                    self._handle_hitl(data)
                elif self.path == "/screenshot":
                    self._handle_screenshot(data)
                elif self.path == "/flutter_error":
                    outer.flutter_errors.append(data)
                    outer.events.append({"type": "flutter_error", "summary": data.get("error", "")[:200]})
                    print(f"[host] Flutter error captured from device: {data.get('error', '')[:160]}")
                    self._send_json(200, {"ok": True})
                elif self.path == "/done":
                    self._send_json(200, {"ok": True})
                else:
                    self._send_json(404, {"error": "not found"})

            def _handle_nav(self, data):
                shot = base64.b64decode(data.get("screenshot_b64", ""))
                target = data.get("target_screen", "")
                guess = data.get("current_screen_guess", "")
                outer.events.append({"type": "nav_request", "target": target, "guess": guess})
                try:
                    action = ai_navigator.decide_next_action(
                        screenshot_bytes=shot,
                        current_screen_guess=guess,
                        target_screen=target,
                        app_map=outer.app_map,
                        documentation=outer.documentation,
                        test_creds=outer.test_creds,
                    )
                except Exception as e:
                    outer.events.append({"type": "nav_error", "error": str(e)})
                    self._send_json(500, {"error": str(e)})
                    return

                # Escalate to HITL on low confidence or destructive action.
                escalate = (
                    action.get("confidence") == "low"
                    or action.get("action") == "hitl"
                    or (action.get("is_destructive") and outer._should_confirm_destructive())
                )
                if escalate:
                    answer = outer._invoke_hitl(
                        kind="nav_confirm",
                        question=(
                            f"AI suggests action='{action.get('action')}' "
                            f"selector='{action.get('selector')}' "
                            f"(target {target}, confidence {action.get('confidence')}). "
                            f"Reasoning: {action.get('reasoning')}\nProceed?"
                        ),
                        meta={"action": action},
                    )
                    if answer.lower() not in ("y", "yes"):
                        action = {"action": "skip", "reasoning": "user declined", "confidence": "high"}
                outer.events.append({"type": "nav_response", "action": action})
                self._send_json(200, action)

            def _handle_verify(self, data):
                shot = base64.b64decode(data.get("screenshot_b64", ""))
                expected = data.get("expected_screen", "")
                try:
                    res = ai_navigator.verify_screen(
                        screenshot_bytes=shot,
                        expected_screen=expected,
                        documentation=outer.documentation,
                    )
                except Exception as e:
                    self._send_json(500, {"error": str(e)})
                    return
                outer.events.append({"type": "verify", "expected": expected, "result": res})
                self._send_json(200, res)

            def _handle_hitl(self, data):
                kind = data.get("kind", "confirm")
                question = data.get("question", "")
                opts = data.get("options")
                ans = outer._invoke_hitl(kind=kind, question=question, meta={}, options=opts,
                                         default=data.get("default"))
                self._send_json(200, {"answer": ans})

            def _handle_screenshot(self, data):
                name = data.get("name", f"shot_{int(time.time())}").replace("/", "_")
                shot = base64.b64decode(data.get("screenshot_b64", ""))
                # Convention: <screen>_<resolution>.png; on real device default is 'native'.
                screen_part, _, res_part = name.rpartition("_")
                if not screen_part:
                    screen_part, res_part = name, "native"
                target = outer.screenshots_dir / screen_part
                target.mkdir(parents=True, exist_ok=True)
                p = target / f"{res_part}.png"
                p.write_bytes(shot)
                outer.saved_pngs.append(str(p))
                # Quick blank check is local + cheap; vision pass downstream
                # will use this hint to skip wasted calls.
                blank, info = blank_filter.is_blank(p)
                outer.events.append({"type": "screenshot", "path": str(p), "blank": blank, "info": info})
                self._send_json(200, {"saved_path": str(p), "blank": blank})

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        print(f"[server] listening on http://{self.host}:{self.port}")

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    # ---------- HITL plumbing ----------
    def _invoke_hitl(self, *, kind: str, question: str, meta: dict,
                     options: list[str] | None = None,
                     default: str | None = None) -> str:
        if self.on_hitl:
            return self.on_hitl(kind, question, {"meta": meta, "options": options, "default": default})
        # Fallback: terminal prompts.
        if options:
            return hitl.ask_choice(question, options)
        if kind == "ask_text":
            return hitl.ask_text(question, default=default)
        return "yes" if hitl.confirm(question, default=False) else "no"

    def _should_confirm_destructive(self) -> bool:
        import os
        return os.getenv("FLOWTEST_AUTO_CONFIRM_DESTRUCTIVE", "false").lower() not in ("y", "yes", "true", "1")
