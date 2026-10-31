# HI Scenario Builder

The HI Scenario Builder is a research prototype for describing a small Hybrid Intelligence (HI) scenario, checking its RDF against the existing HI shapes, and exploring its team in a knowledge graph. It gives researchers a controlled path from a form to inspectable RDF and a saved GraphDB graph.

The [hosted MVP](https://hi-project-demo.duckdns.org) is an authenticated research demonstration, not a production service. Access credentials are distributed separately.

## Researcher workflow

The Svelte interface can load the bundled S1 example or a local JSON file, and download the current draft as JSON. A researcher edits the form, validates and previews the generated N-Triples without saving, then explicitly saves a new scenario. The Explore step queries the saved team composition (CQ1) and links to its named graph in GraphDB Workbench. Editing the form hides stale preview, save, and query results. The backend is the authoritative validator; the UI's checks provide immediate feedback.

The application API enforces **create-only** saving: each scenario ID identifies one stored graph, and submitting an existing ID returns `409`, even for identical JSON. Direct GraphDB administrators can still change or delete graphs. The interface offers *Save as new scenario* to assign a new ID. It does not list or reopen stored scenarios for editing, so keep downloaded JSON drafts. If a write times out, check `GET /scenarios/{scenario_id}/team` or the named graph in Workbench before trying again; its outcome may be uncertain.

## Scenario and semantic scope

The current JSON model contains one use case, an implicit HI team, one goal, at least one task, and at least two agents including a human and an artificial agent. Agents have names and one or more HINT roles; the use case, goal, and tasks use HINT concepts, with an optional use-case domain. Goals and tasks have optional English descriptions, stored separately from their names as `rdfs:comment` literals. An optional Context adds a HINT context concept, multiple phenomena and constraints, and an optional English description. Its identity is scoped to the scenario (`…:context`), like the implicit team. Optional capabilities are independent entities with stable IDs and HINT concepts, linked to any number of existing agents and tasks. Optional task executions each identify one existing task and performing agent, a HINT TaskExecution concept, and an optional Method concept. Unknown fields, duplicate entity IDs within each kind, and unknown references are rejected. Existing JSON that omits optional collections remains valid. [S1 example](examples/s1.json) includes the original Context, four capabilities, three executions, three experiments, three evaluations, and one interaction and preserves all 120 asserted S1 triples in [the research scenarios](ontology/scenarios_kgs.ttl), modulo application-assigned entity IRIs, plus seven example labels (127 triples total). This preserves the source assertions without resolving inherited ontology or research modelling issues.

The task inventory is separate from the goal's requirements. Optional `goal.required_tasks` lists the IDs of tasks explicitly required by the goal; it must be nonempty, unique, and reference existing tasks. Omitting it retains legacy behavior: all scenario tasks are required. The form initializes legacy imports with all tasks selected and exports an explicit selection. Added tasks start unselected; deleting a task removes its reference, and at least one requirement must remain. Executions may realize tasks outside this selection.

When Context is present, the app always asserts team → `hi:operatesInContext` → context and context → `hi:hasInfluenceOn` → team as an S1-based modelling assumption; source scenarios such as S5 do not explicitly include the latter fact.

Capability links explicitly generate both `hi:allowsTask` and its inverse `hi:requiresCapability` because queries disable inference. Possessing a capability does not assign an agent to a task or calculate eligibility. Removing an agent or task in the form removes its capability links; capability identities remain independent of their concepts and links.

Executions explicitly link both performer directions and target the scenario's existing goal. Several executions may realize the same task, including repeated executions by one agent. Deleting a referenced agent or task preserves execution data and shows the missing reference; preview and saving require repairing the reference or removing the execution. No capability eligibility calculation is performed.

Optional experiments store HINT concepts, metrics, and nonblank null/alternative hypotheses. Evaluations link one experiment to any number of executions through `hi:evaluatedBy`, with their own HINT concept, metrics, and optional English description. An evaluation can be shared across executions. Deleting an experiment or execution preserves evaluations and requires explicit reference repair. Both hypotheses use either plain literals (the default) or English tags (`hypothesis_language: "en"`), matching the source scenarios. Tagged source hypotheses are preserved despite the ontology's declared `xsd:string` range; they are not silently converted to plain text.

Optional interactions have a HINT intent and modality, at least two distinct existing participants, optional execution links, and an optional English description. Participants are explicitly selected and never inferred from performers. Interactions can share executions or have no execution links; duplicate references are rejected. Deleting a referenced agent or execution preserves interaction data and exposes missing links for repair before preview/save. Intent and modality must belong to their HINT categories; scenario-local intent IRIs are not accepted as substitutes.

The S2 source assertion `InteractionExplainRisk hi:towardsGoal GoalSafeToolRetrieval` is not currently represented because its intended semantics require clarification: the ontology declares `hi:towardsGoal` for TaskExecution, whereas this subject is an Interaction.

The pipeline validates JSON, checks each HINT concept against the checked-in thesaurus, converts to RDF, and runs the existing SHACL shapes with `inference="none"` and no OWL imports. N-Triples output is sorted for reproducibility. Application-assigned entity IDs remain stable across renames and produce IRIs under `urn:hi-app:scenario:{scenario-id}:…`, scoped by scenario and entity kind. Names, kinds, and roles do not define identity, and agents in different scenarios are not asserted to be the same individual. Ontology terms use `https://w3id.org/hi-ontology#`; HINT concepts use the actual thesaurus IRIs under `https://w3id.org/hi-thesaurus/` (despite `#` in its metadata).

SHACL conformance means only that the current shapes passed; it is not a check of full ontology completeness. Context vocabulary is checked by Python; the existing shapes contain no Context-specific constraints. These shapes do not require task capabilities, and their `hi:Execution` target differs from the ontology's `hi:TaskExecution`; Python validates execution references and concepts. GraphDB repository `hi` uses the `empty` ruleset with `owl:sameAs` optimization disabled; application queries use explicit named graphs and `infer=false`. This avoids currently questionable inferences, including the ontology domain of `hi:operatesInContext` classifying teams as agents. Inference would not repair the SHACL mismatch or turn OWL minimum cardinalities into closed-world checks.

The original ontology and HINT files are loaded into separate reference graphs (`urn:hi-app:reference:ontology` and `urn:hi-app:reference:hint`). Each saved scenario occupies `urn:hi-app:graph:scenario:{scenario-id}`. CQ1 keeps each member IRI, so agents sharing a name, type, or role remain distinct. Agent names come from scenario RDF; type labels come from the ontology and role labels/definitions from HINT. Missing labels are returned as `null`, not invented.

## Run locally

Use Python 3.11+, Node 20.19+ or 22.12+, and Docker with Compose. From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
docker compose up -d --wait --wait-timeout 180
.\.venv\Scripts\python -m infra.graphdb setup
.\.venv\Scripts\python -m uvicorn hi_scenario.api:app --reload --host 127.0.0.1 --port 8000
```

In another terminal, from the repository root:

```powershell
cd frontend
npm ci
npm run dev
```

Open the app at `http://localhost:5173`, API documentation at `http://127.0.0.1:8000/docs`, or the local Workbench at `http://127.0.0.1:7200` (select repository `hi`). The local GraphDB port is bound to loopback and has no authentication. `setup` creates the repository when needed and refreshes the two reference graphs without deleting scenario graphs.

For tests, from the repository root:

```powershell
.\.venv\Scripts\python -m pytest -q
cd frontend
npm test
npm run check
npm run test:integration
```

The frontend integration suite starts its own backend. Its GraphDB workflow runs when the local Compose database is reachable and otherwise skips. The ordinary Python suite does not require a live database.

## API

All scenario POST requests accept the same JSON model as [S1](examples/s1.json). The local base URL is `http://127.0.0.1:8000`; deployment serves the API under `/api`.

| Endpoint | Result |
| --- | --- |
| `POST /scenarios/preview` | Validates and returns RDF, triple count, and SHACL report; stores nothing. |
| `POST /scenarios` | Validates and saves a new named graph; returns `201` with repository, graph, and Workbench location. Existing IDs return `409`. |
| `GET /scenarios/{scenario_id}/team` | Runs CQ1 over the saved graph and reference graphs; returns member IRIs, names, types, and roles. Missing IDs return `404`. |

Invalid submissions return structured `422` errors. Save and team requests report GraphDB unavailability as `503` and unexpected database results as `502`. See the running FastAPI `/docs` for field-level schemas.

For the Linux Compose deployment, access controls, data handling, and update procedure, see the [deployment guide](docs/deployment.md).
