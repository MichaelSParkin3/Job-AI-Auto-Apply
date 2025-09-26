from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Any, Dict


def log_event(event: Dict[str, Any]) -> None:
    """Log a structured JSON event to stdout.

    Args:
        event (dict): A dictionary-like object to be serialized as JSON.
    """
    print(json.dumps(event, ensure_ascii=False))


@dataclass
class ApiError:
    """Represents a structured error message, aligned with REST API errors.

    Attributes:
        code (str): A stable, machine-readable error code.
        message (str): A human-readable description of the error.
        details (dict | None): Optional structured data about the error.
        timestamp (str): An ISO-8601 timestamp of when the error occurred.
        requestId (str): A unique ID for tracing the request.
    """
    code: str
    message: str
    details: Dict[str, Any] | None = None
    timestamp: str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    requestId: str = uuid.uuid4().hex

    def to_json(self) -> str:
        """Serialize the error object to a JSON string, nested under an 'error' key.

        Returns:
            str: A JSON representation of the error.
        """
        return json.dumps({"error": asdict(self)}, ensure_ascii=False)

