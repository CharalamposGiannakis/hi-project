"""FastAPI entry point for the frontend integration tests, with Nebula HTTP mocked."""

import json
from pathlib import Path
from unittest.mock import patch

import httpx

from hi_scenario import nebula
from hi_scenario.api import app as app


S1 = json.loads((Path(__file__).resolve().parents[2] / "examples" / "s1.json").read_text(encoding="utf-8"))
REAL_CLIENT = httpx.Client


def _completion(request: httpx.Request) -> httpx.Response:
    assert request.method == "POST"
    assert str(request.url) == "https://nebula.cs.vu.nl/api/chat/completions"
    assert request.headers["Authorization"] == "Bearer integration-test-key"
    payload = json.loads(request.content)
    assert payload["model"] == "integration-test-model"
    description = json.loads(next(message["content"] for message in payload["messages"] if message["role"] == "user"))
    if description["use_case"] == "Provider temporarily unavailable.":
        return httpx.Response(429, text="Synthetic upstream provider detail")

    task = S1["tasks"][0]
    scenario = {
        "use_case": S1["use_case"],
        "goal": {key: S1["goal"][key] for key in ("id", "name", "concept")} | {"required_tasks": [task["id"]]},
        "tasks": [task],
        "agents": S1["agents"],
        "context": {
            "concept": "HealthMonitoringContext",
            "phenomena": ["SensorNoisePhenomenon"],
            "constraints": ["PrivacyConstraint"],
        },
    }
    diagnostics = []
    if "precision ranking" in description["use_case"]:
        scenario = {"use_case": {"id": "precision-ranking", "name": "Precision ranking"}}
        diagnostics = [
            {"kind": "unsupported_vocabulary", "path": "use_case.concept", "message": "Consider precision ranking as a vocabulary suggestion."},
            {"kind": "unsupported_relationship", "message": "The scenario cannot express the proposed joint authority relationship."},
        ]
    else:
        assert description["use_case"] == "A personal assistant HI system for health and lifestyle."
        assert "wellbeing" in description["goal"]
        assert "self-reports" in description["tasks"]
        if "still to be determined" in description["agents"]:
            scenario["agents"] = [agent for agent in S1["agents"] if agent["kind"] == "human"]
            diagnostics = [{"kind": "missing_information", "path": "agents", "message": "Identify an artificial team member and its role."}]
        else:
            assert "AI assistant" in description["agents"]

    content = json.dumps({"scenario": scenario, "diagnostics": diagnostics})
    return httpx.Response(200, json={
        "model": payload["model"], "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
    })


def _fixture_client(*args, **kwargs) -> httpx.Client:
    kwargs["transport"] = httpx.MockTransport(_completion)
    return REAL_CLIENT(*args, **kwargs)


# This module lives only in the isolated preview test process.
patch.object(nebula.httpx, "Client", _fixture_client).start()
