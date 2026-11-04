# HI Scenario Builder

The HI Scenario Builder is a research prototype for describing Hybrid Intelligence (HI) scenarios, validating their RDF against the checked-in HI resources, and exploring saved teams in GraphDB. A Svelte form calls a FastAPI backend that validates JSON and HINT concepts, generates deterministic RDF, runs SHACL, and handles storage and SPARQL queries.

The [hosted MVP](https://hi-project-demo.duckdns.org) is an authenticated research demonstration, not a production service. Credentials are distributed separately.

## Researcher workflow

1. Load the bundled S1 example, open a canonical example or another local JSON file with **Open JSON file…**, or enter a scenario in the form.
2. Edit the scenario in collapsible sections and download its JSON draft. Use **Expand all** / **Collapse all** to navigate; validation opens sections with errors and links to affected fields. Sections can be collapsed while errors remain. HINT details and definitions are available below vocabulary fields. The backend is the authoritative validator; the form provides immediate feedback.
3. Preview the validated N-Triples and SHACL result without saving.
4. Save a new scenario, then use Explore to retrieve its team composition (CQ1) and open its named graph in GraphDB Workbench.

**Open JSON in new tab** opens a read-only snapshot viewer. **Refresh JSON** or reloading the viewer retrieves the latest form state, including unsaved edits, without a backend request. Keep the original Builder tab open; reloading that tab requires opening a new viewer. Snapshots do not update automatically and are not stored in the browser. The viewer requires browser support for BroadcastChannel and reports when it cannot retrieve an update.

Editing the form hides stale preview, save, and query results. The interface does not list or reopen stored scenarios for editing, so keep downloaded drafts. The API enforces **create-only** saving: an existing scenario ID returns `409`, even for identical JSON. Use *Save as new scenario* for a fresh ID. Direct GraphDB administration can bypass this policy. After an uncertain save outcome, check `GET /scenarios/{scenario_id}/team` or the named graph in Workbench before retrying.

## Capabilities and limitations

Each scenario has one use case, an implicit HI team, one goal, at least one task, and at least two named agents including a human and an artificial agent, with HINT roles. Optional components include Context, independent Team constraints, capabilities, task executions and methods, experiments and hypotheses, evaluations and metrics, and multi-agent interactions. Researchers select goal-required tasks separately from the task inventory. Existing JSON that omits optional components remains valid.

Entity identities are application-assigned and scenario-scoped; shared names, types, roles, or HINT concepts do not merge individuals. JSON import/export preserves the representation. See [semantic reconciliation](docs/semantic-reconciliation.md) for model assumptions, literal handling, and source coverage.

- **Validation has limits.** HINT categories and references are checked by Python; passing the existing SHACL shapes does not establish full ontology completeness or research correctness. Some canonical examples retain documented omissions or provisional alignments awaiting Ilaria's confirmation.
- **Only CQ1 is implemented and verified.** It returns actual saved members and their roles, with labels from RDF and HINT. The application does not calculate capability eligibility or infer task performers or interaction participants.
- **Concurrency is limited.** Use one backend worker and one instance. Its save lock is process-local; independent API, importer, or GraphDB administrator writes are not coordinated.
- **There is no administrator-only approval/publication workflow.** The API has no administrator role or approval gate for saves. Deployment authentication provides shared access, without per-researcher roles or an audit trail. Researcher drafts, administrator review, and shared publication are not separated by the current application.

The seven canonical examples are available as JSON:

| Example | Scenario | Generated triples |
| --- | --- | ---: |
| [S1](examples/s1.json) | Personal Assistant HI | 127 |
| [S2](examples/s2.json) | Collaborative Manipulation | 195 |
| [S3](examples/s3.json) | Group Deliberation | 135 |
| [S4](examples/s4.json) | Autonomous Tutoring | 154 |
| [S5](examples/s5.json) | Hybrid Medical Diagnosis | 139 |
| [S6](examples/s6.json) | Campus Energy Negotiation | 150 |
| [S7](examples/s7.json) | Virtual Museum Guide | 173 |

Exact source reconciliation, provisional vocabulary choices, and additional assertions are documented in the [technical reference](docs/semantic-reconciliation.md#scenario-coverage).

## Local setup and testing

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

Open the app at `http://localhost:5173`, API documentation at `http://127.0.0.1:8000/docs`, or Workbench at `http://127.0.0.1:7200` (select repository `hi`). Local GraphDB is unauthenticated and bound to loopback. `setup` creates the repository if needed and refreshes the ontology and HINT reference graphs without deleting scenario graphs. Repository `hi` uses the `empty` ruleset with `owl:sameAs` optimization disabled; queries use explicit named graphs and `infer=false`.

Run the ordinary checks from the repository root:

```powershell
.\.venv\Scripts\python -m pytest -q
cd frontend
npm test
npm run check
npm run build
npm run test:integration
```

The Python suite includes S1–S7 semantic regression tests and does not require a live database. Frontend integration tests start their own backend; the GraphDB workflow skips when the local database is unreachable. For isolated live importer verification, from the repository root:

```powershell
$env:HI_GRAPHDB_LIVE = '1'
.\.venv\Scripts\python -m pytest tests/test_canonical_live.py -q
Remove-Item Env:HI_GRAPHDB_LIVE
```

That test cleans up only its temporary graphs and does not restart GraphDB. The separate opt-in [persistence test](tests/test_graphdb_live.py) restarts local GraphDB; run it only when that interruption is acceptable. Local tests do not establish hosted HTTPS behavior. Persistent volumes, deployment security, and the absence of a verified backup-and-restore procedure are covered in the [deployment runbook](docs/deployment.md).

## Canonical scenario import

The operator-run importer loads exactly `examples/s1.json` through `examples/s7.json` into the **local development Compose** repository `hi`. After local setup, run from the repository root:

```powershell
.\.venv\Scripts\python -m infra.canonical plan
.\.venv\Scripts\python -m infra.canonical apply
.\.venv\Scripts\python -m infra.canonical verify
```

Each graph is `urn:hi-app:graph:scenario:{id}`, with IDs `s1` through `s7` and the counts listed above.

| Operation | Behavior |
| --- | --- |
| `plan` | Read-only. Validates all seven inputs, including model, HINT, SHACL and expected counts; checks repository/reference configuration; compares complete RDF graphs and reports missing, identical, conflicting, or invalid/unavailable states. |
| `apply` | Completes the full preflight before writing. Creates only missing graphs through the guarded create-only adapter, skips identical graphs, and refuses all writes on preflight errors or conflicts. Verifies the corpus after import. |
| `verify` | Read-only. Checks exact counts, RDF isomorphism, entity identities, SHACL, and CQ1 members/roles against canonical RDF and reference labels. Independently checks both reference graphs against the checked-in originals. |

Imports are **idempotent**: repeating `apply` on an identical corpus creates nothing. The importer never clears or replaces graphs, writes reference or unrelated graphs, or performs setup, reference refresh, or restart. After a failure it reports confirmed creations and any uncertain save outcome; inspect with `plan`/`verify`, then rerun `apply` to resume. Investigate conflicts rather than overwriting them. Errors/conflicts return a nonzero exit status; missing graphs are a successful plan but fail verification.

The importer accepts only `GRAPHDB_URL=http://127.0.0.1:7200` or `http://localhost:7200` and `GRAPHDB_REPOSITORY=hi`. It follows no redirects and uses no proxy settings. Use the local Compose service, **never a tunnel to another environment**; this utility does not authorize remote or deployment imports. Development and deployment have separate volumes, as described in the [runbook](docs/deployment.md#storage-access-and-updates).

Run `apply` as the **sole writer**, with API/UI saves, other importers, and direct Workbench edits paused. The process-local save lock does not provide a transaction spanning the corpus or coordinate other processes.

Importing these curated reference scenarios does **not** approve researcher submissions or implement administrator-only publication. The save API and UI authorization behavior are unchanged. Broader CQ investigation is tracked in [Issue #15](https://github.com/CharalamposGiannakis/hi-project/issues/15); other unresolved work belongs in [GitHub Issues](https://github.com/CharalamposGiannakis/hi-project/issues). The [reference document](docs/semantic-reconciliation.md#competency-query-coverage) records current CQ coverage and independent offline observations.

## API overview

All scenario POST requests accept the canonical JSON model, as illustrated by [S1](examples/s1.json). The local base URL is `http://127.0.0.1:8000`; deployment serves the API under `/api`.

| Endpoint | Result |
| --- | --- |
| `POST /scenarios/preview` | Validates and returns RDF, triple count, and SHACL report; stores nothing. |
| `POST /scenarios` | Validates and saves a new named graph; returns `201` with repository, graph, and Workbench location. Existing IDs return `409`. |
| `GET /scenarios/{scenario_id}/team` | Runs CQ1 over the saved graph and reference graphs; returns member IRIs, names, types, and roles. Missing IDs return `404`. |

Invalid submissions return structured `422` errors. Save and team requests report GraphDB unavailability as `503` and unexpected database results as `502`. See the running FastAPI `/docs` for field-level schemas.

## Technical documentation

- [Semantic reconciliation](docs/semantic-reconciliation.md): S1–S7 coverage, source exceptions, representation decisions, ontology/SHACL limits, and CQ coverage.
- [Deployment runbook](docs/deployment.md): Linux Compose, HTTPS, authentication, updates, storage, verification, and troubleshooting.
