from pathlib import Path

from fastapi.testclient import TestClient

from apps.preview.main import create_app


def test_preview_flow_round_trip(tmp_path: Path):
    app = create_app(static_dir=tmp_path, demo=True)
    client = TestClient(app)

    create = client.post("/api/run/preview", json={"dryRun": True})
    assert create.status_code == 200
    data = create.json()
    run_id = data["runId"]
    assert data["dryRun"] is True
    assert "screenshotUrl" in data["preview"]

    get_response = client.get(f"/api/run/{run_id}")
    assert get_response.status_code == 200

    approve = client.post(f"/api/run/{run_id}/approve")
    assert approve.status_code == 200

    edit = client.post(f"/api/run/{run_id}/edit", json={"text": "Needs tweak"})
    assert edit.status_code == 200

    abort = client.post(f"/api/run/{run_id}/abort")
    assert abort.status_code == 200

    updates = client.get(f"/api/run/{run_id}/updates")
    assert updates.status_code == 200
    assert len(updates.json()["events"]) >= 1


def test_missing_ui_returns_hint(tmp_path: Path):
    # Provide a static directory that does not contain index.html to trigger hint
    empty_dir = tmp_path / "static"
    empty_dir.mkdir()
    app = create_app(static_dir=empty_dir, demo=True)
    client = TestClient(app)

    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "missing_ui"
