from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Any, Dict


def log_event(event: Dict[str, Any]) -> None:
    """Log a structured JSON event to stdout."""
    print(json.dumps(event, ensure_ascii=False))


@dataclass
class ApiError:
    code: str
    message: str
    details: Dict[str, Any] | None = None
    timestamp: str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    requestId: str = uuid.uuid4().hex

    def to_json(self) -> str:
        return json.dumps({"error": asdict(self)}, ensure_ascii=False)

