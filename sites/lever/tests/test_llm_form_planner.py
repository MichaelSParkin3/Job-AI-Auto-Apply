import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.getcwd())

from core.autofill.planner import AutofillPlannerConfig, AutofillPlannerOrchestrator  # noqa: E402
from sites.lever.form_executor import LeverFormPlanner  # noqa: E402


@pytest.fixture()
def selectors_path(tmp_path: Path) -> Path:
    return Path(__file__).resolve().parents[3] / "sites" / "lever" / "selectors" / "form-fields.json"


def _load_fixture(name: str) -> str:
    fixture_path = Path(__file__).resolve().parent / "fixtures" / name
    return fixture_path.read_text(encoding="utf-8")


def _build_orchestrator() -> AutofillPlannerOrchestrator:
    config = AutofillPlannerConfig(model="stub", enable_llm=False)
    return AutofillPlannerOrchestrator(config=config, llm_client=None)


@pytest.mark.parametrize(
    "fixture_name",
    ["modal_form.html", "full_page_form.html"],
)
def test_enriched_plan_variants(selectors_path: Path, fixture_name: str) -> None:
    planner = LeverFormPlanner.load(selectors_path)
    html = _load_fixture(fixture_name)
    plan = planner.plan_from_html(html)
    orchestrator = _build_orchestrator()
    result = orchestrator.build_plan(
        candidate_id="fixture-candidate",
        dom_html=html,
        plan=plan,
        answer_metadata={},
    )
    assert result.intents, "enriched plan should include intents"
    assert len(result.intents) == len(plan.fields)
    assert result.llm_used is False
    payload = {
        "candidateId": "fixture-candidate",
        "fields": [intent.value_key for intent in result.intents],
    }
    assert json.dumps(payload)
