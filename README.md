# HI Scenario Builder

[![CI](https://github.com/CharalamposGiannakis/hi-project/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/CharalamposGiannakis/hi-project/actions/workflows/ci.yml)

[![Recovery rehearsal](https://github.com/CharalamposGiannakis/hi-project/actions/workflows/recovery.yml/badge.svg?branch=main)](https://github.com/CharalamposGiannakis/hi-project/actions/workflows/recovery.yml)

The HI Scenario Builder is a research prototype for describing Hybrid Intelligence (HI) scenarios and validating their RDF against the checked-in HI resources. A Svelte wizard and structured editor share a JSON draft. FastAPI validates canonical scenario JSON and HINT concepts, generates deterministic RDF, and runs SHACL. The Knowledge Explorer queries and compares validated provisional session scenarios and authorized shared knowledge in GraphDB.

The [hosted MVP](https://hi-project-demo.duckdns.org) is an authenticated research demonstration, not a production service. Credentials are distributed separately.

## Researcher workflow

Home is the default landing page. Use the application sidebar to open the Scenario Builder, Scientific Knowledge Management, or Knowledge Explorer. Hide or show navigation from the page heading to make more room for your work. The Builder places validation and JSON beside the editor when the available workspace is wide enough, and below it on smaller screens. Scientific Knowledge Management currently shows a planned-feature placeholder. Switching views preserves the open Builder and Explorer session state.

1. In **Describe with AI**, choose **Write full description** to type or paste a scenario, or use **Previous** and **Next** to answer the optional guided questions. Use **Add additional notes** for supplementary information. **View full description** and the JSON preview show the text from all three inputs.
2. Choose **Convert to JSON using AI** to send your description to VU Nebula. Review the proposed facts and HINT mappings in the Structured Editor. **Scenario JSON** holds interpretation findings about missing or unsupported information. Review the source evidence before accepting any proposed scientific fact.
3. Switch to **Structured Editor** at any point to add or edit HINT-backed fields. Use **Expand all** or **Collapse all** to navigate the eleven sections. Your answers and structured edits stay available as you switch between input methods. **Load S1 example** opens the bundled canonical scenario.
4. Choose **Validate Scenario** when you're ready for a technical check. Follow diagnostics to fields that need correction. A valid result includes N-Triples and the SHACL report. Choose **Add to Knowledge Explorer →** to add a selected provisional snapshot and open the Explorer. Editing the structured scenario makes its validation stale, so validate again before adding another snapshot. Scientific approval is a separate process.
5. In **Knowledge Explorer**, select session scenarios, shared knowledge, or both. Select a competency question and any HINT filters, then choose **Run Query**. Each result identifies its source scenario and links its evidence to RDF identifiers. Returning to **Scenario Builder** keeps the open draft and edits. You can load or create another scenario, validate it, and add another independent snapshot.
6. Use **Find concepts** to select a capability, constraint, method, or metric across the chosen scenarios. Use **Compare scenarios** to select two sources, including at least one session scenario, and inspect which concepts are recorded in both sources or in only one. Each row retains its entity, recorded relationship, source status, and RDF evidence.
7. In the Explorer, select multiple JSON files with **Upload scenario files**. Canonical JSON and Pillar 1 draft exports with a complete scenario are accepted. Each file receives a technical check and joins the same provisional session collection as Builder snapshots. Select or deselect entries for CQ execution and concept search, compare selected sources, or remove entries from the session.

**Download JSON** saves incomplete descriptions and partial candidates. A draft holds the full description, guided answers, and notes in `source_description` and the editable candidate in `scenario`. The `interpretation` record retains the text sent to Nebula, the generated candidate, findings, model identifier, and prompt version. When the description or candidate has changed, those findings refer to the original proposal. After the structured scenario passes local form checks, **Download canonical JSON** exports the scenario for use with the API. **Open JSON file…** accepts either format.

**Open JSON in new tab** opens a read-only snapshot viewer. **Refresh JSON** or reloading the viewer retrieves the latest draft directly from the open Builder tab. Reloading the Builder requires opening a new viewer. The viewer uses BroadcastChannel and keeps its snapshot in memory until you refresh or close it.

Open **Researcher feedback** in the sidebar or **Share feedback** on Home to report a problem, suggest an improvement, or share a scientific observation. Send only information authorized for operator review. Only the selected type, application area, and message are submitted; scenario contents, browser details, and researcher identity are not attached. A successful submission shows a reference ID. Failed submissions retain the message, and unsent text survives navigation but not a reload.

Feedback is persistent and private to operators, separate from scenarios, GraphDB, scientific approval, and GitHub Issues. The API accepts submissions and provides no feedback retrieval endpoints. Local startup stores records in ignored `.local/feedback`; `FEEDBACK_DIR` overrides the directory. Deployment uses a dedicated backend volume. Operators review, export, and restore feedback using the [feedback runbook](docs/deployment.md#feedback-review-and-recovery); GraphDB backups do **not** include it.

## Capabilities and limitations

Each scenario has one use case, an implicit HI team, one goal, at least one task, and at least two named agents including a human and an artificial agent, with HINT roles. Optional components include Context, independent Team constraints, capabilities, task executions and methods, experiments and hypotheses, evaluations and metrics, and multi-agent interactions. Researchers select goal-required tasks separately from the task inventory. Existing JSON that omits optional components remains valid.

Entity identities are application-assigned and scenario-scoped; shared names, types, roles, or HINT concepts do not merge individuals. JSON import/export preserves the representation. See [semantic reconciliation](docs/semantic-reconciliation.md) for model assumptions, literal handling, and source coverage.

- **Validation has limits.** HINT categories and references are checked by Python; passing the existing SHACL shapes does not establish full ontology completeness or research correctness. Some canonical examples retain documented omissions or provisional alignments awaiting Ilaria's confirmation.
- **Interpretations need review.** Nebula can miss, misclassify, or introduce facts. Use the source description, proposal, and findings to check the result. The full description is sent to Nebula when you request interpretation. Submit only content authorized for that service. [VU Nebula](https://rdm.vu.nl/tools/nebula/index.html)
- **Explorer coverage.** All twelve original questions are listed. CQ1 lists team members and roles. CQ2 derives team coverage of recorded requirements. CQ5 follows execution-linked interactions. CQ6 follows methods to recorded executions, tasks, and goals. CQ7 follows evaluation and experiment metrics to assessed task executions, keeping metric sources distinct. CQ8 retrieves goal-linked experiments, metrics, and hypotheses. CQ9 shows contextual constraints and recorded influence links. CQ10 finds constraints shared by at least two distinct use-case identities and shows associated team members. CQ11 lists contextual phenomena. CQ3, CQ4, and CQ12 display **Scientific review pending** with an explanation. Capability coverage, contextual association, and a recorded method do not establish performance, causation, or effectiveness.
- **Provisional session scenarios.** Explicitly added Builder snapshots and validated JSON uploads stay in browser memory through navigation. Reloading or closing the app clears them. Each entry is an independent snapshot, so later Builder edits preserve previously added content. Every selected entry is revalidated and staged in the query transaction, which is rolled back. Duplicate scenario IDs retain their canonical identities and receive separate source and graph identifiers. CQ10 determines distinctness by use-case identifiers without comparing scenario content. Copies retaining the same use-case identifier cannot satisfy its distinctness condition. Different identifiers may represent identical scientific content.
- **Generated goal and influence links.** The canonical RDF generator assigns `towardsGoal` links to executions and adds `hasInfluenceOn` when a scenario contains a context. CQ6 and CQ9 expose these application representation conventions. Independent scientific evidence is required to establish that a method achieves a goal or that a context influences a team.
- **Concept comparison.** Cross-scenario exploration covers capabilities, team and context constraints, execution methods, and evaluation and experiment metrics. Common concepts share an exact HINT identifier and category. Their recorded relationships remain visible for each source. Vocabulary overlap alone does not establish scientific equivalence, transferability, or effectiveness. A concept recorded only in one source may be missing from the other description. Results display up to 200 relationship rows and flag truncation. Some selected scenarios may not appear when this limit is exceeded.
- **Concurrency is limited.** Use one backend worker and one instance. Its save lock is process-local; independent API, importer, or GraphDB administrator writes are not coordinated.
- **Publication is operator configured.** The Explorer labels saved scenarios as approved using `GRAPHDB_APPROVED_SCENARIO_IDS`. The operator must verify Ilaria's scientific approval of the exact stored content before configuring it. This list carries no approval evidence, reviewer identity, or version binding. With no available approved scenarios, the Explorer uses the bundled S1–S7 experimental references and warns if configured IDs resolved to none. Provisional session scenarios and bundled references are staged in a GraphDB transaction for the query and rolled back. Deployment authentication provides shared access, without per-researcher accounts or a review workflow.

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

To try the workflow, load S1 in the Builder, choose **Validate Scenario**, then **Add to Knowledge Explorer →**. Return to the Builder, open `examples/s2.json`, validate it, and add it. Select both session entries and run CQ1 to inspect their separate provenance. Return to the Builder and edit S2. Its validation becomes stale while the previously added S2 snapshot retains its original content. Try deselecting or removing an entry, and use the combined source option to query session scenarios alongside the shared corpus. Nebula and the canonical importer are optional for this walkthrough.

In **Find concepts**, search the experimental references for **Knowledge Graph Querying Capability** to find S2, S4, S5, S6, and S7. Search **Privacy Constraint** to find S1, S4, S5, and S7 and inspect its team or context attachment. In **Compare scenarios**, select an added session snapshot and shared S5 to review common and source-specific concepts and their evidence. An approved corpus configured by the operator changes the shared scenarios available to these searches.

To check JSON uploads, select `examples/s2.json` and `examples/s5.json` together. Select both entries alongside any Builder-added snapshots and query them with the shared references. Try CQ6 with **Knowledge Graph Query Method**, CQ7 with **Diagnosis Accuracy Metric**, and CQ9/CQ10 with **Privacy Constraint**. Select CQ3 to inspect its pending status. Invalid or incomplete files show per-file validation errors.

For local AI interpretation, create a private `.env.nebula` in the repository root with your Nebula key. Start Uvicorn as shown above. The backend reads the file automatically when you request interpretation. The model setting is optional and defaults to `FAST.gpt-oss:120b`.

```dotenv
NEBULA_API_KEY=<your-nebula-api-key>
NEBULA_MODEL=FAST.gpt-oss:120b
```

Explicit process environment values take precedence. The local file is ignored by Git and excluded from Docker builds. The Structured Editor and technical validation remain available without a Nebula key.

Run the ordinary checks from the repository root:

```powershell
.\.venv\Scripts\python -m pytest -q
cd frontend
npm test
npm run check
npm run build
npm run test:integration
```

The Python suite includes S1–S7 semantic regression tests. Standard tests use simulated provider responses and run without a Nebula key. Frontend integration tests start their own backend. The GraphDB workflow skips when the local database is unreachable. To evaluate the live interpreter with the backend key configured, run the opt-in checks for complete, incomplete, and unsupported scenarios:

```powershell
$env:HI_NEBULA_LIVE = '1'
.\.venv\Scripts\python -m pytest tests/test_nebula_live.py -q -s
Remove-Item Env:HI_NEBULA_LIVE
```

For isolated live importer verification, from the repository root:

```powershell
$env:HI_GRAPHDB_LIVE = '1'
.\.venv\Scripts\python -m pytest tests/test_canonical_live.py -q
Remove-Item Env:HI_GRAPHDB_LIVE
```

That test cleans up only its temporary graphs and does not restart GraphDB. The separate opt-in [persistence test](tests/test_graphdb_live.py) restarts local GraphDB; run it only when that interruption is acceptable. Local tests do not establish hosted HTTPS behavior. The [deployment runbook](docs/deployment.md) covers persistent volumes, deployment security, and the [local recovery rehearsal](docs/deployment.md#local-graphdb-recovery-rehearsal).

The single-server container deployment has no Azure service dependency. The runbook also covers [migration to another Linux host](docs/deployment.md#migration-to-another-linux-host), including attaching a verified restored GraphDB volume. VU SciCloud access and hosting requirements must be confirmed before choosing target networking, TLS, storage, or changing the current service.

## Automated verification

[CI](.github/workflows/ci.yml) runs on every pull request, pushes to `main`, and manual dispatch, using GitHub-hosted Ubuntu runners with Python 3.12 and Node 22. The checks reuse the local test commands:

| Required PR check | Coverage |
| --- | --- |
| **Backend and semantics** | Python tests, S1–S7 RDF/SHACL, HINT/frontend vocabulary alignment, API and interpretation regressions, recovery guards, and deployment Compose configuration. |
| **Frontend** | Lockfile installation, component tests, Svelte checks, production build, Builder → real FastAPI → RDF/SHACL integration with simulated AI, and feedback form → private storage/recovery integration. |
| **GraphDB integration** | Fresh GraphDB 10.8.14, canonical importer, live competency questions and concept search, provisional-source isolation/rollback, and the frontend API-client workflow. Database unavailability fails this check instead of skipping it. |

The explicitly required Python live suites run through `.github/scripts/required_tests.py`. Collection-time and execution-time skips make that invocation fail, including when other tests pass. The runner does not enable live tests or change their safety prerequisites. Ordinary `python -m pytest` retains the intentional opt-in skips for local testing and the backend check.

[Recovery rehearsal](.github/workflows/recovery.yml) runs on PRs affecting recovery/CI tooling, persistence code, canonical RDF inputs, or container/deployment configuration, as well as each Monday at 05:17 UTC and on manual dispatch. UI-only and documentation-only PRs do not trigger it. It tests concurrency and restart persistence, then runs the existing synthetic capture, checksum, canonical restore and complete-RDF checks before starting the authenticated container application on the restored volume. It verifies restart persistence and Explorer rollback and removes the disposable resources. Recovery remains separate from the three required PR status checks; review its result when it runs for an infrastructure change.

Neither workflow updates the hosted application or uses Azure, VU hosting credentials, production data or a real Nebula key. Live Nebula evaluation remains an explicit researcher/operator check because it requires credentials, incurs provider usage and is nondeterministic. Passing CI checks technical behavior, not scientific approval. Local/container rehearsals do not verify production recovery, DNS or real HTTPS ingress. Workflows use read-only repository permissions and commit-pinned official actions; review and refresh those pins when updating CI dependencies.

The active [Main Branch Protection ruleset](https://github.com/CharalamposGiannakis/hi-project/rules/28262060) protects the default branch, currently `main`. It requires a PR, successful **Backend and semantics**, **Frontend**, and **GraphDB integration** checks with the branch up to date, and resolved review threads. Force pushes and branch deletion are blocked; no bypass actors are configured. An approving review is not currently mandatory. Recovery is not a required status check. These workflows do not change the ruleset or merge/push to `main`.

The owner maintains Actions permissions, fork-workflow approvals and runner/registry availability. Scheduled runs use the default branch; manual dispatch can select a branch once the workflow exists on the default branch. If a merge queue is enabled later, add its `merge_group` event before requiring these checks in the queue.

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

Run `apply` as the **sole writer**, with API writes, other importers, and direct Workbench edits paused. The process-local save lock does not provide a transaction spanning the corpus or coordinate other processes.

Broader CQ investigation is tracked in [Issue #15](https://github.com/CharalamposGiannakis/hi-project/issues/15). Track other unresolved work in [GitHub Issues](https://github.com/CharalamposGiannakis/hi-project/issues). Current CQ coverage and independent offline observations are recorded in the [reference document](docs/semantic-reconciliation.md#competency-query-coverage).

## API overview

Preview and save accept the canonical JSON model illustrated by S1. Interpretation accepts the optional `full_description`, guided answers, and `additional_notes` in a `description` object. The local base URL is `http://127.0.0.1:8000` and deployment serves the API under `/api`. [S1 canonical example](examples/s1.json)

| Endpoint | Result |
| --- | --- |
| `POST /scenarios/interpret` | Requests a proposal from Nebula and returns an editable candidate and findings. |
| `POST /scenarios/preview` | Validates and returns RDF, triple count, and SHACL report; stores nothing. |
| `POST /scenarios` | Validates and saves a new named graph; returns `201` with repository, graph, and Workbench location. Existing IDs return `409`. |
| `GET /scenarios/{scenario_id}/team` | Runs CQ1 over the saved graph and reference graphs; returns member IRIs, names, types, and roles. Missing IDs return `404`. |

The Builder workflow ends at technical validation and export. GraphDB saves and CQ1 queries are available through the API. To save a separate graph, submit canonical JSON with a fresh scenario ID. After an uncertain save outcome, check `GET /scenarios/{scenario_id}/team` or the named graph in Workbench before retrying.

Invalid submissions return structured `422` errors. Save and team requests report GraphDB unavailability as `503` and unexpected database results as `502`. See the running FastAPI `/docs` for field-level schemas.

## Technical documentation

- [Semantic reconciliation](docs/semantic-reconciliation.md): S1–S7 coverage, source exceptions, representation decisions, ontology/SHACL limits, and CQ coverage.
- [Deployment runbook](docs/deployment.md): Linux Compose, HTTPS, authentication, updates, storage, verification, and troubleshooting.
