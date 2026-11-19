import json

import httpx
import pytest

from hi_scenario import nebula
from hi_scenario.model import Scenario
from hi_scenario.vocabulary import export_vocabulary


KEY = "test-nebula-credential"
DESCRIPTION = {"use_case": "  A human and AI work together.\nTask types are undecided.  ", "additional_notes": "Ébauche."}


@pytest.fixture
def stub_nebula(monkeypatch):
    """Exercise the real HTTP client request and response handling without using the network."""
    client = httpx.Client
    monkeypatch.setenv("NEBULA_API_KEY", KEY)
    monkeypatch.delenv("NEBULA_MODEL", raising=False)

    def install(handler):
        requests = []

        def intercept(request):
            requests.append(request)
            return handler(request)

        def connect(**options):
            return client(transport=httpx.MockTransport(intercept), **options)

        monkeypatch.setattr(nebula.httpx, "Client", connect)
        return requests

    return install


def completion(content, finish_reason="stop"):
    return httpx.Response(200, json={"choices": [{
        "finish_reason": finish_reason, "message": {"content": content},
    }]})


def test_request_includes_exact_answers_canonical_schema_and_all_hint_concepts(stub_nebula):
    result = {"scenario": {"tasks": []}, "diagnostics": []}
    requests = stub_nebula(lambda _: completion(json.dumps(result)))

    assert nebula.request_interpretation(DESCRIPTION) == ("FAST.gpt-oss:120b", result)
    (request,) = requests
    assert request.method == "POST"
    assert str(request.url) == "https://nebula.cs.vu.nl/api/chat/completions"
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    payload = json.loads(request.content)
    assert payload["model"] == "FAST.gpt-oss:120b"
    assert payload["temperature"] == 0
    system, user = payload["messages"]
    assert (system["role"], user["role"]) == ("system", "user")
    assert json.loads(user["content"]) == DESCRIPTION
    assert KEY not in system["content"] and KEY not in user["content"]
    instructions, _, schemas = system["content"].partition("Complete canonical Scenario JSON schema:\n")
    schema_text, _, hint_text = schemas.partition(
        "\n\nComplete approved HINT vocabulary (IDs, labels, and source definitions by category):\n"
    )
    assert json.loads(schema_text) == Scenario.model_json_schema()
    vocabulary = json.loads(hint_text)
    assert vocabulary == json.loads(export_vocabulary())
    assert len(vocabulary) == 16
    assert sum(map(len, vocabulary.values())) == 215
    assert "formal assignment alone" in instructions
    assert "goal.required_tasks" in instructions
    assert "unsupported_relationship" in instructions
    assert "A single named agent is enough to return a draft" in instructions


def test_configured_model_and_fenced_json(stub_nebula, monkeypatch):
    monkeypatch.setenv("NEBULA_MODEL", "custom-model")
    requests = stub_nebula(lambda _: completion('```json\n{"scenario": null, "diagnostics": []}\n```'))
    assert nebula.request_interpretation(DESCRIPTION) == ("custom-model", {"scenario": None, "diagnostics": []})
    assert json.loads(requests[0].content)["model"] == "custom-model"


def test_missing_key_keeps_backend_usable_and_does_not_send_a_request(stub_nebula, monkeypatch):
    monkeypatch.delenv("NEBULA_API_KEY")
    requests = stub_nebula(lambda _: pytest.fail("Unconfigured interpretation must not contact Nebula"))
    with pytest.raises(nebula.NebulaError) as error:
        nebula.request_interpretation(DESCRIPTION)
    assert error.value.status_code == 503
    assert requests == []


@pytest.mark.parametrize("status", [302, 401, 403, 429, 500])
def test_provider_errors_do_not_expose_raw_response_or_follow_redirects(stub_nebula, status):
    requests = stub_nebula(lambda _: httpx.Response(
        status, text=f"Provider debug output with {KEY}", headers={"Location": "https://example.invalid/"},
    ))
    with pytest.raises(nebula.NebulaError) as error:
        nebula.request_interpretation(DESCRIPTION)
    assert error.value.status_code == 502
    assert KEY not in str(error.value)
    assert "Provider debug output" not in str(error.value)
    assert len(requests) == 1


@pytest.mark.parametrize(("failure", "status"), [(httpx.ConnectError, 502), (httpx.ReadTimeout, 504)])
def test_provider_transport_failure_has_a_safe_message(stub_nebula, failure, status):
    def fail(_):
        raise failure(f"Provider debug output with {KEY}")

    stub_nebula(fail)
    with pytest.raises(nebula.NebulaError) as error:
        nebula.request_interpretation(DESCRIPTION)
    assert error.value.status_code == status
    assert KEY not in str(error.value)


@pytest.mark.parametrize("response", [
    httpx.Response(200, text="not an API response"),
    httpx.Response(200, json={"choices": []}),
    completion(None),
    completion("Provider text before a JSON object: {}"),
    completion('{"value": NaN}'),
    completion('{"scenario": null, "diagnostics": []}', finish_reason="length"),
])
def test_malformed_outputs_and_truncated_completions_are_rejected(stub_nebula, response):
    stub_nebula(lambda _: response)
    with pytest.raises(nebula.NebulaError) as error:
        nebula.request_interpretation(DESCRIPTION)
    assert error.value.status_code == 502
