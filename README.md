# HI Scenario Builder

The HI Scenario Builder is a research prototype for describing Hybrid Intelligence (HI) scenarios and validating their RDF against the checked-in HI resources. A Svelte wizard and structured editor share a JSON draft. FastAPI validates canonical scenario JSON and HINT concepts, generates deterministic RDF, and runs SHACL. The API also supports GraphDB storage and team-composition queries.

The [hosted MVP](https://hi-project-demo.duckdns.org) is an authenticated research demonstration, not a production service. Credentials are distributed separately.

## Researcher workflow

1. In **Describe with AI**, choose **Write full description** to type or paste a scenario, or use **Previous** and **Next** to answer the optional guided questions. Use **Add additional notes** for supplementary information. **View full description** and the JSON preview show the text from all three inputs.
2. Choose **Convert to JSON using AI** to send your description to VU Nebula. Review the proposed facts, HINT mappings, and any missing or unsupported information. A partial proposal can open in the Structured Editor and be corrected. Review the source evidence before accepting any proposed scientific fact.
3. Switch to **Structured Editor** at any point to add or edit HINT-backed fields. Use **Expand all** or **Collapse all** to navigate the eleven sections. Your answers and structured edits stay available as you switch between input methods. **Load S1 example** opens the bundled canonical scenario.
4. Choose **Validate Scenario** when you're ready for a technical check. Follow diagnostics to fields that need correction. A valid result includes N-Triples and the SHACL report. Editing the structured scenario clears that result. Scientific approval is a separate process.

**Download JSON** saves incomplete descriptions and partial candidates. A draft holds the full description, guided answers, and notes in `source_description` and the editable candidate in `scenario`. The `interpretation` record retains the text sent to Nebula, the generated candidate, findings, model identifier, and prompt version. When the description or candidate has changed, those findings refer to the original proposal. After the structured scenario passes local form checks, **Download canonical JSON** exports the scenario for use with the API. **Open JSON file…** accepts either format.

**Open JSON in new tab** opens a read-only snapshot viewer. **Refresh JSON** or reloading the viewer retrieves the latest draft directly from the open Builder tab. Reloading the Builder requires opening a new viewer. The viewer uses BroadcastChannel and keeps its snapshot in memory until you refresh or close it.

## Capabilities and limitations

Each scenario has one use case, an implicit HI team, one goal, at least one task, and at least two named agents including a human and an artificial agent, with HINT roles. Optional components include Context, independent Team constraints, capabilities, task executions and methods, experiments and hypotheses, evaluations and metrics, and multi-agent interactions. Researchers select goal-required tasks separately from the task inventory. Existing JSON that omits optional components remains valid.

Entity identities are application-assigned and scenario-scoped; shared names, types, roles, or HINT concepts do not merge individuals. JSON import/export preserves the representation. See [semantic reconciliation](docs/semantic-reconciliation.md) for model assumptions, literal handling, and source coverage.

- **Validation has limits.** HINT categories and references are checked by Python; passing the existing SHACL shapes does not establish full ontology completeness or research correctness. Some canonical examples retain documented omissions or provisional alignments awaiting Ilaria's confirmation.
- **Interpretations need review.** Nebula can miss, misclassify, or introduce facts. Use the source description, proposal, and findings to check the result. The full description is sent to Nebula when you request interpretation. Submit only content authorized for that service. [VU Nebula](https://rdm.vu.nl/tools/nebula/index.html)
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
