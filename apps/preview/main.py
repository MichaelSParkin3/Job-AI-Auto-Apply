from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

PLACEHOLDER_SCREENSHOT_DATA_URI = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
)
PLACEHOLDER_SUMMARY = (
    "Dry-run preview generated for demo purposes. This snapshot represents the "
    "final review step the automation captured before submission."
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


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def create_app(*, static_dir: Path | None = None, demo: bool = True) -> FastAPI:
    """Create the FastAPI application that backs the preview experience."""

    app = FastAPI(
        title="Job AI Auto Apply Preview API",
        version="0.1.0",
        description="Local-only API for preview approvals and demo flows",
    )

    run_store: Dict[str, Dict[str, object]] = {}
    app.state.run_store = run_store

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

    @app.post("/api/run/preview")
    async def create_preview(payload: PreviewRequest) -> Dict[str, object]:
        run_id = uuid.uuid4().hex
        run_data = {
            "id": run_id,
            "status": "review",
            "dryRun": bool(payload.dryRun or demo),
            "createdAt": _now_iso(),
            "preview": {
                "screenshotUrl": PLACEHOLDER_SCREENSHOT_DATA_URI,
                "summary": PLACEHOLDER_SUMMARY,
                "notes": "Approve, edit, or abort using shortcuts.",
            },
            "events": [
                RunEvent(
                    type="preview.created",
                    message="Preview run created in demo mode.",
                    at=_now_iso(),
                ).model_dump(),
            ],
        }
        run_store[run_id] = run_data
        return {
            "runId": run_id,
            "status": run_data["status"],
            "preview": run_data["preview"],
            "dryRun": run_data["dryRun"],
        }

    @app.get("/api/run/{run_id}")
    async def get_run(run_id: str) -> Dict[str, object]:
        if run_id not in run_store:
            raise HTTPException(status_code=404, detail="Run not found")
        return run_store[run_id]

    def _append_event(run_id: str, event: RunEvent) -> None:
        run_store[run_id]["events"].append(event.model_dump())

    @app.post("/api/run/{run_id}/approve")
    async def approve_run(run_id: str) -> Dict[str, object]:
        if run_id not in run_store:
            raise HTTPException(status_code=404, detail="Run not found")
        run_store[run_id]["status"] = "approved"
        _append_event(
            run_id,
            RunEvent(
                type="preview.approved",
                message="User approved preview in demo mode (no submission performed).",
                at=_now_iso(),
            ),
        )
        time.sleep(0.25)
        return {"ok": True, "status": "approved"}

    @app.post("/api/run/{run_id}/edit")
    async def edit_run(run_id: str, body: EditRequest) -> Dict[str, object]:
        if run_id not in run_store:
            raise HTTPException(status_code=404, detail="Run not found")
        run_store[run_id]["status"] = "editing"
        run_store[run_id]["preview"]["edits"] = body.text
        _append_event(
            run_id,
            RunEvent(
                type="preview.edited",
                message="User provided manual edit in demo mode.",
                at=_now_iso(),
            ),
        )
        return {"ok": True, "status": "editing"}

    @app.post("/api/run/{run_id}/abort")
    async def abort_run(run_id: str) -> Dict[str, object]:
        if run_id not in run_store:
            raise HTTPException(status_code=404, detail="Run not found")
        run_store[run_id]["status"] = "aborted"
        _append_event(
            run_id,
            RunEvent(
                type="preview.aborted",
                message="User aborted the dry-run.",
                at=_now_iso(),
            ),
        )
        return {"ok": True, "status": "aborted"}

    @app.get("/api/run/{run_id}/updates")
    async def updates(run_id: str) -> Dict[str, List[Dict[str, object]]]:
        if run_id not in run_store:
            raise HTTPException(status_code=404, detail="Run not found")
        return {"events": run_store[run_id]["events"]}

    return app