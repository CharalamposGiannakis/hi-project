# HI Scenario Builder

The HI Scenario Builder is a research prototype for describing a small Hybrid Intelligence (HI) scenario, checking its RDF against the existing HI shapes, and exploring its team in a knowledge graph. It gives researchers a controlled path from a form to inspectable RDF and a saved GraphDB graph.

The [hosted MVP](https://hi-project-demo.duckdns.org) is an authenticated research demonstration, not a production service. Access credentials are distributed separately.

## Researcher workflow

The Svelte interface can load the bundled S1 example or a local JSON file, and download the current draft as JSON. A researcher edits the form, validates and previews the generated N-Triples without saving, then explicitly saves a new scenario. The Explore step queries the saved team composition (CQ1) and links to its named graph in GraphDB Workbench. Editing the form hides stale preview, save, and query results. The backend is the authoritative validator; the UI's checks provide immediate feedback.

The application API enforces **create-only** saving: each scenario ID identifies one stored graph, and submitting an existing ID returns `409`, even for identical JSON. Direct GraphDB administrators can still change or delete graphs. The interface offers *Save as new scenario* to assign a new ID. It does not list or reopen stored scenarios for editing, so keep downloaded JSON drafts. If a write times out, check `GET /scenarios/{scenario_id}/team` or the named graph in Workbench before trying again; its outcome may be uncertain.

## Scenario and semantic scope

The current JSON model contains one use case, an implicit HI team, one goal, at least one task, and at least two agents including a human and an artificial agent. Agents have names and one or more HINT roles; the use case, goal, and tasks use HINT concepts, with an optional use-case domain. Goals and tasks have optional English descriptions, stored separately from their names as `rdfs:comment` literals. An optional Context adds a HINT context concept, multiple phenomena and constraints, and an optional English description. Its identity is scoped to the scenario (`…:context`), like the implicit team. Optional capabilities are independent entities with stable IDs and HINT concepts, linked to any number of existing agents and tasks. Optional task executions each identify one existing task and performing agent, a HINT TaskExecution concept, and an optional Method concept. Unknown fields, duplicate entity IDs within each kind, and unknown references are rejected. Existing JSON that omits optional collections remains valid. [S1 example](examples/s1.json) includes the original Context, four capabilities, three executions, three experiments, three evaluations, and one interaction and preserves all 120 asserted S1 triples in [the research scenarios](ontology/scenarios_kgs.ttl), modulo application-assigned entity IRIs, plus seven example labels (127 triples total). This preserves the source assertions without resolving inherited ontology or research modelling issues.

The task inventory is separate from the goal's requirements. Optional `goal.required_tasks` lists the IDs of tasks explicitly required by the goal; it must be nonempty, unique, and reference existing tasks. Omitting it retains legacy behavior: all scenario tasks are required. The form initializes legacy imports with all tasks selected and exports an explicit selection. Added tasks start unselected; deleting a task removes its reference, and at least one requirement must remain. Executions may realize tasks outside this selection.

Optional `team_constraints` selects HINT Constraint concepts directly on the existing Team. It defaults to empty for older JSON and is independent of `context.constraints`. Team constraints can be used without Context; removing or changing Context preserves Team selections.

When Context is present, the app always asserts team → `hi:operatesInContext` → context and context → `hi:hasInfluenceOn` → team as an S1-based modelling assumption; source scenarios such as S5 do not explicitly include the latter fact.

Capability links explicitly generate both `hi:allowsTask` and its inverse `hi:requiresCapability` because queries disable inference. Possessing a capability does not assign an agent to a task or calculate eligibility. Removing an agent or task in the form removes its capability links; capability identities remain independent of their concepts and links.

Executions explicitly link both performer directions and target the scenario's existing goal. Several executions may realize the same task, including repeated executions by one agent. Deleting a referenced agent or task preserves execution data and shows the missing reference; preview and saving require repairing the reference or removing the execution. No capability eligibility calculation is performed.

Optional experiments store HINT concepts, metrics, and nonblank null/alternative hypotheses. Evaluations link one experiment to any number of executions through `hi:evaluatedBy`, with their own HINT concept, metrics, and optional English description. An evaluation can be shared across executions. Deleting an experiment or execution preserves evaluations and requires explicit reference repair. Both hypotheses use either plain literals (the default) or English tags (`hypothesis_language: "en"`), matching the source scenarios. Tagged source hypotheses are preserved despite the ontology's declared `xsd:string` range; they are not silently converted to plain text.

Optional interactions have a HINT intent and modality, at least two distinct existing participants, optional execution links, and an optional English description. Participants are explicitly selected and never inferred from performers. Interactions can share executions or have no execution links; duplicate references are rejected. Deleting a referenced agent or execution preserves interaction data and exposes missing links for repair before preview/save. Intent and modality must belong to their HINT categories; scenario-local intent IRIs are not accepted as substitutes.

The [S2 example — Collaborative Manipulation](examples/s2.json) is available through **Open JSON file…**. It preserves all 40 entities and 181/182 original source assertions, plus 14 application display labels, producing **195 triples**. Its ten tasks have exactly three direct goal requirements; heavy lifting has two executions, and tool retrieval has none. Names supply application labels rather than original research assertions. The sole omitted source assertion, `InteractionExplainRisk hi:towardsGoal GoalSafeToolRetrieval`, remains a research-model exception requiring clarification: the ontology declares `hi:towardsGoal` for TaskExecution, whereas this subject is an Interaction.

The [S3 canonical example — Group Deliberation](examples/s3.json) is also available through **Open JSON file…**. It represents all 24 original entities and generates **135 triples**: 124/125 original assertions unchanged, one provisional concept substitution, one logically entailed capability inverse, and nine application labels. The source IRI `https://w3id.org/hi-thesaurus/AssessCommunicationAccuracyTask` is undefined; the example uses `https://w3id.org/hi-thesaurus/AssessCommunicationAccuracy` instead. This is a provisional project assumption **pending research-owner confirmation**, not a correction of the research files or an assertion that the IRIs are formally equivalent. The additional `TaskAssessCommunicationAccuracy hi:requiresCapability CapabilityMetaAnalysis` triple follows from the source's `hi:allowsTask` assertion and the ontology's inverse axiom.

The [S4 canonical example — Autonomous Tutoring](examples/s4.json) is available through **Open JSON file…**. It represents all 26 original entities and preserves **142/142 source assertions**, including the seven English descriptions, producing **154 triples**. The additions are ten application display labels and two `hi:hasAgentConcept` links: AITutor → `hint:ArtificialAgent` and HumanLearner → `hint:HumanAgent`. These links are category-consistent application conventions derived from agent kind; they are absent from the source and are not logically entailed by the ontology.

The [S5 canonical example — Hybrid Medical Diagnosis](examples/s5.json), available through **Open JSON file…**, represents all 24 original entities and preserves **126/129 source assertions unchanged**, generating **139 triples**. Two provisional substitutions use generic `hint:Evaluation` in place of Metric-category `hint:DiagnosisAccuracyMetric` and `hint:ExplanationClarityMetric` as evaluation concepts; their metric links remain intact. Generic Evaluation is selectable in the form. This is **pending research-owner clarification**, not an assertion of equivalence. The undeclared `InteractionClinicalDialogue hi:hasInteractionConcept hint:Interaction` assertion is omitted as an unresolved source exception. Additions comprise eight display labels and three existing application conventions: the two agent-concept links derived from agent kind and Context → Team `hi:hasInfluenceOn`. These conventions are absent from S5 and are not logically entailed source assertions.

The [S6 canonical example — Campus Energy Negotiation](examples/s6.json), available through **Open JSON file…**, represents all 26 original entities and preserves **139/139 source assertions**, producing **150 triples** with no source omissions or provisional concept substitutions. Additions are nine display labels and two agent-concept links: AIBuildingAgent → `hint:ArtificialAgent` and HumanGridOperator → `hint:HumanAgent`. These are application conventions derived from agent kind, not logically entailed source assertions. The source HINT identifiers `AllocationNegotationTask` and `NegotationImpactEvaluation` are retained exactly, and both hypotheses remain plain literals without language tags or explicit datatypes.

The [S7 canonical example — Virtual Museum Guide](examples/s7.json), available through **Open JSON file…**, represents all 29 explicitly typed source entities and preserves **157/160 assertions unchanged**, generating **173 triples**. Three provisional replacements use `hint:GuideIntent` and `hint:AnswerIntent` for the source's two unresolved local references, `hi-s7:IntentGuide` and `hi-s7:IntentAnswer`, and `hint:DataCollectionMethod` for undefined `hint:SelfReportingMethod`. These choices remain **pending research-owner clarification** and assert no equivalence. No assertion is omitted without replacement; all three Team and three Context constraint assertions are preserved separately. Additions are ten display labels, the logically entailed `TaskSemanticRetrieval hi:requiresCapability CapabilityKGQuery` inverse, and two application conventions: AIVirtualGuide → `hint:ArtificialAgent` and HumanVisitor → `hint:HumanAgent` via `hi:hasAgentConcept`.

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

## Canonical corpus import

The operator-run importer loads exactly `examples/s1.json` through `examples/s7.json` into the **local development Compose** repository `hi`. After the local setup above, run from the repository root:

```powershell
.\.venv\Scripts\python -m infra.canonical plan
.\.venv\Scripts\python -m infra.canonical apply
.\.venv\Scripts\python -m infra.canonical verify
```

`plan` is read-only: it validates all seven inputs (model, HINT, SHACL and expected counts), checks repository/reference configuration, and classifies each complete RDF graph as missing, identical, or conflicting. `apply` performs that full preflight before writing, creates only missing graphs through the existing guarded adapter, skips identical graphs, and refuses all writes if any input or graph conflicts. It then verifies the corpus. Repeating `apply` creates nothing. No operation clears or replaces graphs; the two reference graphs and unrelated scenarios are never written. A failed import reports confirmed creations and any uncertain save outcome; inspect with `plan`/`verify`, then rerun `apply` to resume. Conflicts require operator investigation, not automatic repair.

| Scenario | Named graph | Triples |
| --- | --- | ---: |
| S1 | `urn:hi-app:graph:scenario:s1` | 127 |
| S2 | `urn:hi-app:graph:scenario:s2` | 195 |
| S3 | `urn:hi-app:graph:scenario:s3` | 135 |
| S4 | `urn:hi-app:graph:scenario:s4` | 154 |
| S5 | `urn:hi-app:graph:scenario:s5` | 139 |
| S6 | `urn:hi-app:graph:scenario:s6` | 150 |
| S7 | `urn:hi-app:graph:scenario:s7` | 173 |

`verify` is read-only and checks exact counts, RDF isomorphism, entity identities, SHACL, and CQ1 membership/roles against the canonical RDF and reference labels. Both reference graphs are independently compared with the checked-in originals. Exit status is nonzero for errors/conflicts; missing graphs are a successful plan but fail verification. The importer refuses `GRAPHDB_URL` other than `http://127.0.0.1:7200` or `http://localhost:7200`, and `GRAPHDB_REPOSITORY` other than `hi`; it does not follow redirects or use proxy settings. Use the local Compose service, never a tunnel to another environment. Run `apply` as the **sole writer**, with API/UI saves, other importers, and direct Workbench edits paused: the existing save lock is process-local, not a transaction spanning the corpus. No repository setup, reference refresh, or restart is performed by the importer.

Only **CQ1 (team composition and roles)** is implemented and verified. The research `TEST/HI-Ontology-Test/cqs.ipynb` also defines capability/task matching (CQ2), candidate teams (CQ3), interactions (CQ5), methods (CQ6), metrics (CQ7), experiments/hypotheses (CQ8), constraints (CQ9–10), and phenomena (CQ11). These are candidates for named-graph adaptation and research validation, not supported application queries. CQ5's required task comments/goal links exclude some source interactions; CQ10's query does not establish shared constraints by itself. CQ4 requires eligibility/assignment rules absent from the `empty` ruleset, and CQ12 concerns compliance data not represented here. None of CQ2–12 is verified by this utility.

This is a curated reference-corpus import, **not administrator approval or publication of research submissions**. The save API and UI behavior are unchanged and provide no administrator-only publication policy. Separation of researcher drafts, administrator review, and shared publication remains a separate high-priority workflow requirement. The scenario-specific source exceptions and provisional alignments above still apply.

For isolated live importer tests (temporary graphs cleaned up; no restart), use `HI_GRAPHDB_LIVE=1` with `python -m pytest tests/test_canonical_live.py -q`. The existing `tests/test_graphdb_live.py` additionally restarts local GraphDB to test persistence; run it only when that interruption is acceptable.

## API

All scenario POST requests accept the same JSON model as [S1](examples/s1.json). The local base URL is `http://127.0.0.1:8000`; deployment serves the API under `/api`.

| Endpoint | Result |
| --- | --- |
| `POST /scenarios/preview` | Validates and returns RDF, triple count, and SHACL report; stores nothing. |
| `POST /scenarios` | Validates and saves a new named graph; returns `201` with repository, graph, and Workbench location. Existing IDs return `409`. |
| `GET /scenarios/{scenario_id}/team` | Runs CQ1 over the saved graph and reference graphs; returns member IRIs, names, types, and roles. Missing IDs return `404`. |

Invalid submissions return structured `422` errors. Save and team requests report GraphDB unavailability as `503` and unexpected database results as `502`. See the running FastAPI `/docs` for field-level schemas.

For the Linux Compose deployment, access controls, data handling, and update procedure, see the [deployment guide](docs/deployment.md).
