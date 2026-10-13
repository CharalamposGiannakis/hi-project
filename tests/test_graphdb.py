import httpx
import pytest
from rdflib import Graph, Literal, Namespace

from infra import graphdb


@pytest.fixture
def server():
    state = {
        "exists": False,
        "params": {"ruleset": {"value": "empty"}, "disableSameAs": {"value": "true"}},
        "graphs": {},
        "requests": [],
    }

    def handle(request):
        state["requests"].append(request)
        if request.method == "GET" and request.url.path == "/rest/repositories/hi":
            return httpx.Response(200, json={"params": state["params"]}) if state["exists"] else httpx.Response(404)
        if request.method == "POST" and request.url.path == "/rest/repositories":
            state["exists"] = True
            return httpx.Response(201)
        if request.method == "PUT" and request.url.path == "/repositories/hi/statements":
            state["graphs"][request.url.params["context"]] = request.content
            return httpx.Response(204)
        pytest.fail(f"Unexpected request: {request.method} {request.url}")

    with httpx.Client(base_url=graphdb.BASE_URL, transport=httpx.MockTransport(handle)) as client:
        yield client, state


def test_repository_config_preserves_explicit_identity_and_named_graph_policy():
    config = Graph().parse(graphdb.ROOT / "infra" / "hi-repository.ttl", format="turtle")
    rep = Namespace("http://www.openrdf.org/config/repository#")
    settings = Namespace("http://www.ontotext.com/config/graphdb#")
    assert set(config.objects(None, rep.repositoryID)) == {Literal("hi")}
    assert set(config.objects(None, settings.ruleset)) == {Literal("empty")}
    assert set(config.objects(None, settings["disable-sameAs"])) == {Literal("true")}
    assert set(config.objects(None, settings["enable-context-index"])) == {Literal("true")}
    assert not list(config.objects(None, settings.imports))


def test_setup_creates_repository_and_uploads_original_bytes_to_separate_graphs(server):
    client, state = server
    graphdb.setup_repository(client)
    creates = [r for r in state["requests"] if r.method == "POST"]
    assert len(creates) == 1
    assert (graphdb.ROOT / "infra" / "hi-repository.ttl").read_bytes() in creates[0].content
    assert set(state["graphs"]) == {f"<{iri}>" for _, iri in graphdb.REFERENCES}
    for path, iri in graphdb.REFERENCES:
        assert state["graphs"][f"<{iri}>"] == path.read_bytes()
    assert all(r.headers["content-type"] == "text/turtle" for r in state["requests"] if r.method == "PUT")


def test_rerunning_setup_replaces_reference_graphs_and_preserves_scenarios(server):
    client, state = server
    graphdb.setup_repository(client)
    scenario_context = "<urn:hi-app:graph:scenario:existing>"
    state["graphs"][scenario_context] = b"existing scenario data"
    before = dict(state["graphs"])
    state["requests"].clear()
    graphdb.setup_repository(client)
    assert state["graphs"] == before
    assert not any(r.method == "POST" for r in state["requests"])
    writes = [r for r in state["requests"] if r.method == "PUT"]
    assert len(writes) == 2
    assert all(r.url.params["context"] != scenario_context for r in writes)


@pytest.mark.parametrize("params", [
    {"ruleset": {"value": "owl2-rl"}, "disableSameAs": {"value": "true"}},
    {"ruleset": {"value": "empty"}, "disableSameAs": {"value": "false"}},
    {},
])
def test_setup_refuses_incompatible_existing_inference_without_writing(server, params):
    client, state = server
    state.update(exists=True, params=params)
    with pytest.raises(RuntimeError, match="will not change an existing repository"):
        graphdb.setup_repository(client)
    assert all(r.method == "GET" for r in state["requests"])


@pytest.mark.parametrize("status_code", [401, 500])
def test_setup_does_not_treat_access_or_server_errors_as_missing_repository(status_code):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(status_code)

    with httpx.Client(base_url=graphdb.BASE_URL, transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            graphdb.setup_repository(client)
    assert len(requests) == 1
    assert requests[0].method == "GET"


def test_readiness_timeout_is_reported():
    with httpx.Client(base_url=graphdb.BASE_URL, transport=httpx.MockTransport(lambda _: httpx.Response(503))) as client:
        with pytest.raises(RuntimeError, match="GraphDB is not ready"):
            graphdb.wait_for_server(client, timeout=0)
