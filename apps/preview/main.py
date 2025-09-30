from __future__ import annotations

import time
import uuid
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import types

try:  # pragma: no cover - exercised when FastAPI is not installed
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
except ModuleNotFoundError:  # pragma: no cover - optional dependency guard
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: object | None = None) -> None:
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class FastAPI:  # type: ignore[override]
        def __init__(self, *args, **kwargs) -> None:
            self.state = types.SimpleNamespace()
            self._routes: Dict[tuple[str, str], callable] = {}

        def mount(self, *_args, **_kwargs) -> None:
            return None

        def get(self, path: str, **_kwargs):
            def decorator(func):
                self._routes[("GET", path)] = func
                return func

            return decorator

        def post(self, path: str, **_kwargs):
            def decorator(func):
                self._routes[("POST", path)] = func
                return func

            return decorator

    class FileResponse:  # pragma: no cover - simple placeholder
        def __init__(self, path: Path | str, *args, **kwargs) -> None:
            self.path = Path(path)

    class StaticFiles:  # pragma: no cover - simple placeholder
        def __init__(self, *args, **kwargs) -> None:
            pass

    class JSONResponse:  # pragma: no cover - simple placeholder
        def __init__(self, content: Dict[str, Any], status_code: int) -> None:
            self.content = content
            self.status_code = status_code

from pydantic import BaseModel, Field

from apps.cli.history_store import HistoryWriter
from apps.cli.queue_manager import ReviewQueueManager, SubmissionDecision
from apps.cli.run_store import RunRecord, RunStore, format_profile_label
from apps.cli.runtime_state import RunContext
from apps.cli.utils import log_event
from .constants import (
    PLACEHOLDER_NOTES,
    PLACEHOLDER_SCREENSHOT_DATA_URI,
    PLACEHOLDER_SUMMARY,
)

DEFAULT_STATIC_DIR = Path(__file__).resolve().parent.parent / "ui" / "dist"


class PreviewRequest(BaseModel):
    searchUrl: Optional[str] = Field(default=None, alias="searchUrl")
    limit: int = Field(default=1, ge=1)
    profileId: Optional[str] = Field(default=None, alias="profileId")
    dryRun: bool = Field(default=True, alias="dryRun")


class EditRequest(BaseModel):
    text: str = Field(..., min_length=1)


class RunEvent(BaseModel):
    type: str
    message: str
    at: str


class DecisionRequest(BaseModel):
    decisionId: str = Field(..., alias="decisionId")
    candidateId: str = Field(..., alias="candidateId")
    outcome: str
    mode: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    rationale: str
    requestedChanges: Optional[List[Dict[str, Any]]] = Field(default=None, alias="requestedChanges")
    timestamp: Optional[str] = Field(default=None)

    def to_decision(self) -> SubmissionDecision:
        timestamp = self.timestamp or _now_iso()
        requested = None
        if isinstance(self.requestedChanges, list):
            requested = [dict(item) for item in self.requestedChanges]
        return SubmissionDecision(
            decision_id=self.decisionId,
            candidate_id=self.candidateId,
            outcome=self.outcome,
            mode=self.mode,
            confidence=self.confidence,
            rationale=self.rationale,
            timestamp=timestamp,
            requested_changes=requested,
        )


class ApiHttpException(HTTPException):
    """Wrap structured API errors for consistent JSON responses."""

    def __init__(self, status_code: int, payload: Dict[str, Any]) -> None:
        super().__init__(status_code=status_code, detail=payload.get("error"))
        self.payload = payload


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _api_error(
    status_code: int,
    code: str,
    message: str,
    *,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    payload = {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "timestamp": _now_iso(),
            "requestId": uuid.uuid4().hex,
        }
    }
    raise ApiHttpException(status_code=status_code, payload=payload)


def create_app(
    *,
    static_dir: Path | None = None,
    demo: bool = True,
    run_store: RunStore | None = None,
    run_record: RunRecord | None = None,
    history_writer: HistoryWriter | None = None,
    run_context: RunContext | None = None,
) -> FastAPI:
    """Create the FastAPI application that backs the preview experience."""

    app = FastAPI(
        title="Job AI Auto Apply Preview API",
        version="0.1.0",
        description="Local-only API for preview approvals and demo flows",
    )

    if hasattr(app, "exception_handler"):

        @app.exception_handler(ApiHttpException)
        async def _handle_api_error(_request, exc: ApiHttpException) -> JSONResponse:  # type: ignore[override]
            return JSONResponse(status_code=exc.status_code, content=exc.payload)

    persistent = run_store is not None and run_record is not None
    run_state: Dict[str, Dict[str, Any]] = {}
    app.state.memory_runs = run_state
    app.state.session_complete = False
    app.state.finalized = False
    app.state.run_record = run_record
    app.state.history_writer = history_writer
    app.state.run_context = run_context
    app.state.persistent = persistent

    resolved_static = static_dir or DEFAULT_STATIC_DIR
    index_file = resolved_static / "index.html"

    if resolved_static.exists() and index_file.exists():
        app.mount(
            "/ui",
            StaticFiles(directory=resolved_static, html=True),
            name="ui",
        )

        @app.get("/", include_in_schema=False)
        async def spa_index() -> FileResponse:
            return FileResponse(index_file)

    else:
        @app.get("/", include_in_schema=False)
        async def spa_index_missing() -> Dict[str, str]:
            message = "UI build not found. Run `pnpm --filter @app/ui build` to generate static assets."
            return {
                "message": message,
                "status": "missing_ui",
                "staticDir": str(resolved_static),
            }

    def _sync_persistent_state() -> Dict[str, Any]:
        if not persistent or run_store is None or run_record is None:
            raise HTTPException(status_code=503, detail="Demo run not initialized")
        payload = run_store.load_run_payload(run_record)
        preview = payload.get("preview", {})
        state = run_state.setdefault(run_record.id, {"id": run_record.id, "events": []})
        payload_metadata = payload.get("metadata") or {}
        state.update(
            {
                "status": payload.get("status", "review"),
                "dryRun": bool(preview.get("dryRun", demo)),
                "preview": {
                    "screenshotUrl": PLACEHOLDER_SCREENSHOT_DATA_URI,
                    "summary": preview.get("summary", PLACEHOLDER_SUMMARY),
                    "notes": preview.get("notes", PLACEHOLDER_NOTES),
                    "edits": preview.get("edits"),
                    "decision": preview.get("decision", "pending"),
                    "decidedAt": preview.get("decidedAt"),
                    "lastEditAt": preview.get("lastEditAt"),
                },
                "metadata": {
                    "profileId": payload.get("profileId"),
                    "profileLabel": payload_metadata.get("profileLabel")
                    or format_profile_label(payload.get("profileId")),
                    "startedAt": payload.get("startedAt"),
                    "limit": payload_metadata.get("limit"),
                    "mode": payload_metadata.get("mode"),
                },
            }
        )
        if payload.get("queue"):
            state["queue"] = payload["queue"]
        return state

    def _assert_run(run_id: str) -> Dict[str, Any]:
        if persistent:
            if run_record is None or run_id != run_record.id:
                _api_error(404, "run_not_found", "Run not found")
            return _sync_persistent_state()
        if run_id not in run_state:
            _api_error(404, "run_not_found", "Run not found")
        return run_state[run_id]

    def _append_event(run_id: str, event: RunEvent) -> None:
        state = run_state.setdefault(run_id, {"id": run_id, "events": []})
        state.setdefault("events", []).append(event.model_dump())
        if persistent and run_record is not None and run_id == run_record.id:
            log_event({
                "event": event.type,
                "message": event.message,
                "timestamp": event.at,
                "mode": "demo",
            })

    @app.post("/api/run/preview")
    async def create_preview(payload: PreviewRequest) -> Dict[str, object]:
        if persistent and run_store is not None and run_record is not None:
            run_store.bootstrap_demo_preview(
                run_record,
                limit=payload.limit,
                profile_id=payload.profileId or run_record.profile_id,
            )
            state = _sync_persistent_state()
            event = RunEvent(
                type="preview.created",
                message="Preview run created in demo mode.",
                at=_now_iso(),
            )
            _append_event(run_record.id, event)
            log_event(
                {
                    "event": "preview.demo_prepared",
                    "message": "Preview session prepared with canned artifacts.",
                    "limit": payload.limit,
                    "profileId": state["metadata"].get("profileId"),
                }
            )
            return {
                "runId": run_record.id,
                "status": state["status"],
                "preview": state["preview"],
                "dryRun": state["dryRun"],
                "metadata": state["metadata"],
            }

        run_id = uuid.uuid4().hex
        created_at = _now_iso()
        payload_metadata = {
            "profileLabel": format_profile_label(payload.profileId),
            "limit": payload.limit,
            "mode": "demo" if payload.dryRun or demo else "standard",
        }
        run_data = {
            "id": run_id,
            "status": "review",
            "dryRun": bool(payload.dryRun or demo),
            "createdAt": created_at,
            "preview": {
                "screenshotUrl": PLACEHOLDER_SCREENSHOT_DATA_URI,
                "summary": PLACEHOLDER_SUMMARY,
                "notes": PLACEHOLDER_NOTES,
            },
            "metadata": {
                "profileId": payload.profileId,
                "profileLabel": payload_metadata["profileLabel"],
                "startedAt": created_at,
                "limit": payload_metadata["limit"],
                "mode": payload_metadata["mode"],
            },
            "events": [
                RunEvent(
                    type="preview.created",
                    message="Preview run created in demo mode.",
                    at=created_at,
                ).model_dump(),
            ],
        }
        run_state[run_id] = run_data
        return {
            "runId": run_id,
            "status": run_data["status"],
            "preview": run_data["preview"],
            "dryRun": run_data["dryRun"],
            "metadata": run_data["metadata"],
        }

    @app.get("/api/run/{run_id}")
    async def get_run(run_id: str) -> Dict[str, object]:
        state = _assert_run(run_id)
        return state

    @app.post("/api/run/{run_id}/approve")
    async def approve_run(run_id: str) -> Dict[str, object]:
        state = _assert_run(run_id)
        if persistent and run_store is not None and run_record is not None:
            run_store.record_demo_decision(run_record, "approved")
            state = _sync_persistent_state()
            app.state.session_complete = True
            if (
                history_writer is not None
                and run_context is not None
                and not getattr(app.state, "finalized", False)
            ):
                history_writer.append_demo_entry(
                    run_context,
                    summary=state["preview"]["summary"],
                    decision="approved",
                    edits=state["preview"].get("edits"),
                )
                app.state.finalized = True
        state["status"] = "approved"
        event = RunEvent(
            type="preview.approved",
            message="User approved preview in demo mode (no submission performed).",
            at=_now_iso(),
        )
        _append_event(run_id, event)
        time.sleep(0.1)
        return {
            "ok": True,
            "status": "approved",
            "message": "Demo preview approved; no submission performed.",
            "decidedAt": state["preview"].get("decidedAt"),
            "preview": state["preview"],
            "metadata": state.get("metadata"),
        }

    @app.post("/api/run/{run_id}/edit")
    async def edit_run(run_id: str, body: EditRequest) -> Dict[str, object]:
        state = _assert_run(run_id)
        if persistent and run_store is not None and run_record is not None:
            run_store.record_demo_edit(run_record, body.text)
            state = _sync_persistent_state()
            state["status"] = "ready"
            if history_writer is not None and run_context is not None:
                history_writer.append_demo_entry(
                    run_context,
                    summary="Manual edit captured for demo preview.",
                    decision="edit",
                    edits=body.text,
                )
        else:
            state["status"] = "ready"
            state.setdefault("preview", {})["edits"] = body.text
        event = RunEvent(
            type="preview.edited",
            message="User provided manual edit in demo mode.",
            at=_now_iso(),
        )
        _append_event(run_id, event)
        return {
            "ok": True,
            "status": "ready",
            "message": "Manual edit captured; retry simulated successfully.",
            "preview": state["preview"],
            "metadata": state.get("metadata"),
        }

    @app.post("/api/run/{run_id}/abort")
    async def abort_run(run_id: str) -> Dict[str, object]:
        state = _assert_run(run_id)
        if persistent and run_store is not None and run_record is not None:
            run_store.record_demo_decision(run_record, "aborted")
            state = _sync_persistent_state()
            app.state.session_complete = True
            if (
                history_writer is not None
                and run_context is not None
                and not getattr(app.state, "finalized", False)
            ):
                history_writer.append_demo_entry(
                    run_context,
                    summary=state["preview"]["summary"],
                    decision="aborted",
                    edits=state["preview"].get("edits"),
                )
                app.state.finalized = True
        state["status"] = "aborted"
        event = RunEvent(
            type="preview.aborted",
            message="User aborted the dry-run.",
            at=_now_iso(),
        )
        _append_event(run_id, event)
        return {
            "ok": True,
            "status": "aborted",
            "message": "Demo preview aborted; automation halted.",
            "preview": state["preview"],
            "metadata": state.get("metadata"),
        }

    @app.get("/api/run/{run_id}/updates")
    async def updates(run_id: str) -> Dict[str, List[Dict[str, object]]]:
        state = _assert_run(run_id)
        return {"events": state.get("events", [])}

    @app.get("/api/queue/{run_id}")
    async def queue_snapshot(run_id: str) -> Dict[str, Any]:
        if persistent and run_store is not None and run_record is not None:
            if run_id != run_record.id:
                _api_error(404, "run_not_found", "Run not found")
            return run_store.load_queue_snapshot(run_record)

        state = _assert_run(run_id)
        queue = state.get("queue")
        if not queue:
            _api_error(404, "queue_not_found", "Queue not found for run")
        return queue

    @app.post("/api/queue/{run_id}/decision")
    async def queue_decision(run_id: str, body: DecisionRequest) -> Dict[str, Any]:
        if persistent and run_store is not None and run_record is not None:
            if run_id != run_record.id:
                _api_error(404, "run_not_found", "Run not found")
            manager = ReviewQueueManager(
                run_store=run_store,
                run_record=run_record,
            )
            decision = body.to_decision()
            try:
                snapshot = manager.record_decision(decision)
            except KeyError:
                _api_error(
                    404,
                    "candidate_not_found",
                    f"Candidate {body.candidateId} not found in queue",
                    details={"candidateId": body.candidateId},
                )
            decision_payload = decision.to_payload()
            stored_decision = run_store.record_submission_decision(
                run_record, decision_payload
            )
            queue_snapshot = snapshot.to_payload()
            state = _sync_persistent_state()
            state["queue"] = queue_snapshot
            if history_writer is not None and run_context is not None:
                run_payload = run_store.load_run_payload(run_record)
                history_writer.append_decision_summary(
                    run_context,
                    run_payload=run_payload,
                    queue_payload=queue_snapshot,
                    decision_payload=stored_decision,
                )
            return {"decision": stored_decision, "queue": state["queue"]}

        state = _assert_run(run_id)
        queue = state.get("queue")
        if not queue:
            _api_error(404, "queue_not_found", "Queue not found for run")
        decision_payload = body.to_decision().to_payload()
        decided = queue.setdefault("decided", [])
        for index, existing in enumerate(decided):
            if existing.get("decisionId") == decision_payload["decisionId"]:
                decided[index] = decision_payload
                break
        else:
            decided.append(decision_payload)
        for candidate in queue.get("pending", []):
            if candidate.get("id") == decision_payload["candidateId"]:
                candidate["lastDecisionId"] = decision_payload["decisionId"]
                if decision_payload["outcome"] == "abort":
                    candidate["state"] = "shelved"
                elif decision_payload["outcome"] == "approve":
                    candidate["state"] = "submitted"
                else:
                    candidate["state"] = "decided"
                break
        queue["lastUpdated"] = decision_payload["timestamp"]
        return {"decision": decision_payload, "queue": queue}

    return app
