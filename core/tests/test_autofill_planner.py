import json
import os
import sys
from typing import Any, Dict

import pytest

sys.path.insert(0, os.getcwd())

from core.autofill.planner import (  # noqa: E402
    AutofillPlannerConfig,
    AutofillPlannerOrchestrator,
)
from sites.lever.form_executor import LeverFieldPlan, LeverFormPlan  # noqa: E402


class StubLLMClient:
    def __init__(self, response: Dict[str, Any]) -> None:
        self._response = response
        self.request: Dict[str, Any] | None = None

    def generate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.request = payload
        return self._response


@pytest.fixture()
def sample_plan() -> LeverFormPlan:
    fields = [
        LeverFieldPlan(label="Full name", selector="input[name='name']", value_key="fullName"),
        LeverFieldPlan(label="Email", selector="input[name='email']", value_key="email"),
        LeverFieldPlan(
            label="Security question",
            selector="textarea[data-qa='security-answer']",
            value_key="securityAnswer",
        ),
    ]
    return LeverFormPlan(fields=fields)


def test_orchestrator_fallback_without_llm(sample_plan: LeverFormPlan) -> None:
    config = AutofillPlannerConfig(model="stub", enable_llm=False)
    orchestrator = AutofillPlannerOrchestrator(config=config, llm_client=None)
    answer_metadata = {
        "fullName": {"status": "resolved", "source": "identity.full_name"},
        "email": {"status": "resolved", "source": "identity.email"},
        "securityAnswer": {"status": "missing", "source": "qa_override"},
    }
    result = orchestrator.build_plan(
        candidate_id="cand-1",
        dom_html="<div>modal</div>",
        plan=sample_plan,
        answer_metadata=answer_metadata,
    )
    assert result.llm_used is False
    assert [intent.strategy for intent in result.intents] == [
        "profile_answer",
        "profile_answer",
        "deterministic_selector",
    ]
    assert result.telemetry.token_usage == {"prompt": 0, "completion": 0, "total": 0}


def test_orchestrator_respects_profile_override(sample_plan: LeverFormPlan) -> None:
    llm_response = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "intents": [
                                {
                                    "key": "securityAnswer",
                                    "strategy": "llm_suggestion",
                                    "confidence": 0.2,
                                }
                            ]
                        }
                    )
                }
            }
        ]
    }
    llm_client = StubLLMClient(llm_response)
    config = AutofillPlannerConfig(model="stub", enable_llm=True)
    orchestrator = AutofillPlannerOrchestrator(config=config, llm_client=llm_client)
    answer_metadata = {
        "securityAnswer": {"status": "resolved", "source": "qa_override"},
    }
    result = orchestrator.build_plan(
        candidate_id="cand-2",
        dom_html="<div>full</div>",
        plan=sample_plan,
        answer_metadata=answer_metadata,
    )
    override_intent = next(intent for intent in result.intents if intent.value_key == "securityAnswer")
    assert override_intent.strategy == "profile_override"
    assert override_intent.confidence == pytest.approx(1.0)


def test_orchestrator_uses_llm_when_available(sample_plan: LeverFormPlan) -> None:
    llm_payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "intents": [
                                {
                                    "key": "email",
                                    "strategy": "llm_email",
                                    "confidence": 0.91,
                                    "field_type": "email",
                                }
                            ]
                        }
                    )
                }
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 4},
    }
    llm_client = StubLLMClient(llm_payload)
    config = AutofillPlannerConfig(model="stub", enable_llm=True)
    orchestrator = AutofillPlannerOrchestrator(config=config, llm_client=llm_client)
    result = orchestrator.build_plan(
        candidate_id="cand-3",
        dom_html="<div>dom</div>",
        plan=sample_plan,
        answer_metadata={"email": {"status": "missing", "source": "profile"}},
    )
    assert result.llm_used is True
    email_intent = next(intent for intent in result.intents if intent.value_key == "email")
    assert email_intent.strategy == "llm_email"
    assert email_intent.confidence == pytest.approx(0.91)
    assert result.telemetry.token_usage == {"prompt": 12, "completion": 4, "total": 16}
    assert result.prompt_records, "LLM execution should capture prompt metadata"
