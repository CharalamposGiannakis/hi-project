# HI Knowledge Graph Population Interface

## Status

Early research prototype. All design, architecture, stack, and interaction choices are **provisional** and should evolve as the project becomes clearer.

T002 implements a local `JSON → RDF → SHACL` flow in `hi_scenario/`. It supports one use case, one implicit HI team, one goal, one or more tasks, and distinct human/artificial agents with names and HINT roles. `examples/s1.json` is a minimal projection of S1 in `ontology/scenarios_kgs.ttl`; its descriptive names are example labels. Context, capabilities, executions, evaluations, and interactions remain outside this representation.

Run from the repository root with Python 3.11+ (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m hi_scenario examples/s1.json --output scenario.nt
.\.venv\Scripts\python -m pytest -q
```

`Scenario.model_validate_json(...)` validates the structure, rejects unhandled fields and duplicate agent/task IDs, and requires both agent kinds. Concept fields and roles use HINT local names, such as `PersonalAssistantUseCase` and `HumanUserRole`; `to_rdf(...)` checks their existence and category against the checked-in thesaurus. Names become `rdfs:label` literals. Application-assigned IDs must be retained across edits: instances use `urn:hi-app:scenario:{scenario-id}:…`, scoped by scenario and entity kind, independently of names, types, and roles. They do not claim the research group's namespace or global agent identity across scenarios.

T004 exposes this same pipeline through `hi_scenario/api.py`. Start the local backend from the repository root:

```powershell
.\.venv\Scripts\python -m uvicorn hi_scenario.api:app --reload --host 127.0.0.1 --port 8000
```

`POST /scenarios/preview` accepts the scenario JSON directly (`Content-Type: application/json`). A `200` response contains `scenario_id`, `rdf_format: "nt"`, `rdf` (sorted N-Triples text), `triple_count`, and `validation: {conforms: true, report: "…"}`. Invalid submissions return `422` with `code`, `message`, `issues`, and `shacl_report`: `invalid_request` includes field issues (`location`, `message`, `type`); `invalid_vocabulary` preserves the converter's explanation; `shacl_failed` includes the SHACL report. Unexpected processing failures return `500` with `internal_error` and a generic message. Nothing is persisted. Interactive API documentation is at `http://127.0.0.1:8000/docs`. CORS allows only the local Svelte development origins (`http://localhost:5173` and `http://127.0.0.1:5173`), so the Vite dev server is pinned to port 5173. The Python test command above includes API tests; `httpx` is required for FastAPI's test client.

T003 adds a Svelte form in `frontend/` that edits the same JSON contract; researchers copy or download the JSON. Nothing is stored or queried. Choice lists come from `frontend/src/lib/hint-vocabulary.json`, generated from the thesaurus with the same category rule as `to_rdf(...)`; a test fails if it is stale. Entity IDs are random, assigned once, and kept across renames. Run with Node 20.19+ or 22.12+:

```powershell
.\.venv\Scripts\python -m hi_scenario.vocabulary frontend/src/lib/hint-vocabulary.json  # after thesaurus changes
cd frontend; npm install; npm run dev    # http://localhost:5173
npm test; npm run check                  # unit tests, type checks
npm run test:integration                 # starts uvicorn itself; PYTHON=… selects the interpreter
```

T005 connects the form to `POST /scenarios/preview` (default `http://127.0.0.1:8000`; override with `VITE_API_URL`). With both servers running, **Validate & preview RDF** shows the backend's SHACL result and N-Triples, or its rejection (field issues, vocabulary message, or SHACL report), or that the backend is unreachable. Local checks still give immediate feedback and block incomplete forms before any request; the backend remains the authoritative validator. A result is shown only while the form's JSON equals the JSON that was validated, so any edit hides an earlier success. Previewing saves nothing. The integration tests mount the real Svelte app in jsdom against a spawned backend and check that the displayed RDF equals the CLI's output for S1.

`to_ntriples(...)` emits sorted N-Triples for reproducible output. The command validates with the unchanged local HI shapes and ontology before writing. Validation adds no inferred facts to the output. SHACL conformance covers the existing constraints, not full ontology completeness: task capabilities are not required by these shapes, and their `hi:Execution` target differs from the ontology's `hi:TaskExecution`. No ontology artefacts have been altered.

T006a adds one local GraphDB service in `compose.yaml`, using the [official image](https://hub.docker.com/r/ontotext/graphdb/) pinned to `10.8.14`. This [10.8 patch release](https://graphdb.ontotext.com/documentation/10.8/release-notes.html) runs in Free mode without supplying a license file; [GraphDB 11 requires a license file even for Free](https://graphdb.ontotext.com/documentation/11.4/set-up-your-license.html). Use Docker Desktop with Linux containers running, plus the Python environment above:

```powershell
docker compose up -d --wait --wait-timeout 180
.\.venv\Scripts\python -m infra.graphdb setup
.\.venv\Scripts\python -m infra.graphdb verify
```

`setup` creates repository `hi` if absent and replaces its two reference graphs with the original file bytes, leaving scenario graphs intact. It refuses an existing repository with incompatible inference settings. `verify` uploads a temporary validated three-agent scenario, reruns setup to check repeatability, restarts this Compose container, queries the scenario together with HINT, and compares all stored RDF with the inputs. It removes only its own temporary graph. It is an explicit integration check; normal pytest tests use mocked HTTP and require no running GraphDB.

Workbench is at `http://127.0.0.1:7200` (choose repository `hi`). Python clients can POST a form field `query` to `http://127.0.0.1:7200/repositories/hi`, accepting `application/sparql-results+json`; RDF writes use `/repositories/hi/statements` with an explicit `context=<graph-IRI>`. Reference knowledge uses `urn:hi-app:reference:ontology` and `urn:hi-app:reference:hint`. Reserve `urn:hi-app:graph:scenario:{scenario-id}` for application scenario graphs, keeping the existing instance IRIs. This establishes storage conventions for the next backend task; the preview API still uses its existing local pipeline. In Workbench, this basic SPARQL query lists the stored graph sizes:

```sparql
SELECT ?graph (COUNT(*) AS ?triples)
WHERE { GRAPH ?graph { ?s ?p ?o } }
GROUP BY ?graph
```

Recommended inference baseline: [`empty` (no reasoning)](https://graphdb.ontotext.com/documentation/10.8/reasoning.html), with `owl:sameAs` optimization disabled. RDFS/rdfsplus would infer that teams using `hi:operatesInContext` are agents because of its current domain; OWL rules can additionally derive property-chain relationships and identity consequences. Those semantics need review before enabling them. Inference does not repair the SHACL execution-class mismatch or make OWL minimum cardinalities closed-world validation. Keep the existing Python SHACL check authoritative and use explicit types or SPARQL property paths for queries requiring superclass traversal.

Data and repository configuration persist in Docker's `hi-project_graphdb-data` named volume, outside Git, across restarts and `docker compose down`/`up`. `docker compose down --volumes` deletes that data. The port is bound only to loopback; this development instance has no authentication. Java heap is limited to 1 GiB; allow additional Docker memory for the process and indexes. Troubleshoot with `docker compose ps` and `docker compose logs graphdb`.

---

## Design Problem

> **How can a researcher describe an HI scenario without having to think like an ontology engineer, while still knowing and controlling what the machine is adding to the shared knowledge graph?**

Target users are **Hybrid Intelligence researchers**. The immediate goal is to make populating the HI Knowledge Graph understandable, interactive, and visually convincing.

---

## Initial Architecture

Two input channels should lead to the **same structured representation**.

```text
                         ┌── Manual structured input
                         │   Sidebar form / JSON editor
Researcher ──────────────┤
                         │
                         └── LLM-assisted description
                                   │
                                   ▼
                         Proposed form values
                                   │
                            Human review/edit
                                   │
                 ┌─────────────────┴─────────────────┐
                 │                                   │
                 │     interaction data recorded     │
                 │  accepted / edited / rejected     │
                 │                                   │
                 └─────────────────┬─────────────────┘
                                   │
                                   ▼
                         Canonical Scenario JSON
                                   │
                          validate / correct
                                   │
                                   ▼
                              JSON → RDF
                                   │
                                SHACL
                                   │
                                   ▼
                            Preview ABox
                                   │
                          Researcher approves
                                   │
                                   ▼
                               GraphDB
                          ┌────────┴────────┐
                          ▼                 ▼
                    SPARQL / query    GraphDB visualisation
                          │
                          ▼
                    Application UI
                          │
                          ▼
                  Own graph visualisation
```

The LLM should `propose values for the same structure used by manual entry`, rather than creating a separate data path.

Human review should remain explicit before anything is committed to the graph.

---

## Interaction Research

The LLM channel can also produce useful interaction data.

For each proposed entry, record whether the researcher:

- accepted it unchanged,
- edited it before accepting,
- rejected it.

This can later support metrics such as **LLM acceptance rate**, correction rate, and acceptance percentage per ontology field or concept.

---

## Graph Interaction

GraphDB can remain directly accessible for researchers who want advanced graph exploration or SPARQL querying.

The application should also provide its own graph visualisation, designed around the current task rather than trying to reproduce all GraphDB functionality.

---

## Suggested Stack

```text
Frontend        Svelte / SvelteKit
Backend         Python + FastAPI
Knowledge Graph GraphDB
Semantic layer  RDF / OWL / SHACL
AI              LLM-assisted structured extraction
```

This is the current preferred direction, not a locked technical decision.

---

## First Deliverables

```text
ontology_map.md
scenario_01_source.ttl
scenario_01.json
json_schema.json
json_to_rdf.py
validation.py
README.md
```

- **ontology_map.md**
Minimal working map of the HI Ontology: important classes, relationships, HINT concepts, validation requirements, and what the UI eventually needs to collect.

- **scenario_01_source.ttl**
One existing valid HI scenario taken from the current knowledge graph and used as the reference case.

- **scenario_01.json**
Human-oriented JSON representation of the same scenario.

- **json_schema.json**
Definition of the canonical structured representation expected from both manual and LLM-assisted input.

- **json_to_rdf.py**
Deterministic conversion from canonical JSON into an HI Ontology ABox.

- **validation.py**
Validation pipeline for generated RDF, initially using the existing SHACL shapes.

- **README.md**
Living notebook of the current project state, decisions, architecture, and next steps.

---

## Next Steps - Current Priority

- **Understand the ontology and one existing scenario** \
Map the relevant ontology structure and reverse-engineer one complete scenario from the existing KG. \
**Goal**: understand exactly what information must be collected from a researcher.


- **Define and validate the canonical JSON representation** \
Represent the selected scenario as JSON and build: \
`JSON → RDF → SHACL validation` \
**Goal**: reproduce a valid ABox without depending on any UI or LLM.

- **Design the researcher interaction** \
Once the required information is understood, design the manual form, LLM-assisted filling, review interaction, ABox preview, and graph visualisation. \
**Goal**: produce one strong end-to-end vertical slice before expanding the system.

---

## MVP Principle

`Build one complete scenario well before supporting the whole ontology.`

The first milestone is not a production system. It is a convincing researcher-facing prototype that demonstrates how the HI Knowledge Graph can grow through understandable and controlled human interaction.
