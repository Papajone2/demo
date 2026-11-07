"""Bounded JSON-lines protocol. No shell, eval, seed export or remote button API."""
import json
from collections import deque

MAX_FRAME = 70000  # Bounded Solana message payloads, never private keys.


class Protocol:
    def __init__(self, controller):
        self.controller = controller
        self.seen = set()
        self.order = deque()

    def handle(self, line):
        request_id = None
        try:
            if len(line) > MAX_FRAME:
                raise ValueError("Frame too large")
            request = json.loads(line)
            if not isinstance(request, dict) or set(request) - {"v", "id", "method", "params"}:
                raise ValueError("Invalid request envelope")
            request_id = request.get("id")
            if not isinstance(request_id, str) or not 1 <= len(request_id) <= 64:
                request_id = None
                raise ValueError("Request ID required")
            if request.get("v") != 1:
                raise ValueError("Unsupported protocol version")
            if request_id in self.seen:
                raise ValueError("Duplicate request ID")
            if not isinstance(request.get("method"), str) or not isinstance(request.get("params", {}), dict):
                raise ValueError("Invalid method or parameters")
            if len(self.order) == 8192:
                self.seen.discard(self.order.popleft())
            self.seen.add(request_id)
            self.order.append(request_id)
            result = self.controller.request(request["method"], request.get("params", {}), request_id)
            return dict(v=1, id=request_id, ok=True, result=result)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            return dict(v=1, id=request_id, ok=False, error=str(exc)[:160])
