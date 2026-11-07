# Deploying the HI Scenario Builder

This runbook describes the existing single-server Linux Compose deployment in [`compose.deploy.yaml`](../compose.deploy.yaml). It runs the Svelte app behind Caddy, one FastAPI backend worker, and GraphDB 10.8.14. It does not provision a server or domain.

## Prepare the server

Install Docker Engine with the Compose plugin. The operator account needs permission to access the Docker daemon; prefix the Docker commands below with `sudo` where necessary. Allow enough memory for GraphDB's configured 1 GiB Java heap **plus** the database, Docker, backend, and web server overhead. Provide durable disk space for Docker volumes. Create DNS records for separate application and Workbench hostnames pointing to the server; allow inbound TCP 80 and 443 so Caddy can obtain and renew HTTPS certificates. Real-domain certificate issuance has not been verified by the local deployment tests.

For an initial deployment or update, obtain the reviewed ref and exact commit SHA from the project owner. From the repository root, fetch that ref, check for local changes, check out the reviewed commit, and confirm the SHA before building. Replace the two example values; resolve local changes without discarding `.env.deploy` or volumes, and do not force the checkout.

```bash
reviewed_ref='your-reviewed-branch-or-tag'
reviewed_commit='full-reviewed-commit-sha'
git fetch origin "$reviewed_ref"
git status --short
git switch --detach "$reviewed_commit"
git rev-parse HEAD
```

Use a private, owner-readable `.env.deploy` beside the Compose file. It is ignored by Git and excluded from Docker builds. Replace every placeholder in this example before starting:

```dotenv
APP_SITE_ADDRESS=https://<app-host>
WORKBENCH_SITE_ADDRESS=https://<workbench-host>
WORKBENCH_PUBLIC_URL=https://<workbench-host>
APP_AUTH_USER=<app-user>
APP_AUTH_PASSWORD_HASH='<app-bcrypt-hash>'
WORKBENCH_AUTH_USER=<operator-user>
WORKBENCH_AUTH_PASSWORD_HASH='<operator-bcrypt-hash>'
```

`APP_SITE_ADDRESS` and `WORKBENCH_SITE_ADDRESS` are Caddy site addresses; `WORKBENCH_PUBLIC_URL` is the browser-facing address returned by the API, not GraphDB's internal URL. Use different credentials for the app and Workbench. Generate each hash interactively with the pinned Caddy image:

```bash
docker run --rm -it caddy:2.11.6-alpine caddy hash-password
chmod 600 .env.deploy
```

Enter each password at Caddy's hidden prompt. Keep the resulting bcrypt hash **single-quoted** in `.env.deploy` so Compose does not expand its `$` characters. Do not place passwords on a command line. `HTTP_BIND` and `HTTPS_BIND` optionally override the default published ports 80 and 443; normal HTTPS deployment should use those defaults.

## Start and manually verify HTTPS

From the repository root on the server:

```bash
docker compose --env-file .env.deploy -f compose.deploy.yaml config -q
docker compose --env-file .env.deploy -f compose.deploy.yaml up -d --build --wait
docker compose --env-file .env.deploy -f compose.deploy.yaml ps
```

The backend starts after GraphDB is healthy, creates repository `hi` if needed, checks its `empty` ruleset and disabled `owl:sameAs` optimization, and loads the original ontology and HINT files into separate reference graphs. Every backend start refreshes those reference graphs; existing scenario graphs remain. Compose sets `GRAPHDB_URL=http://graphdb:7200`, `GRAPHDB_REPOSITORY=hi`, and `GRAPHDB_WORKBENCH_URL` from `WORKBENCH_PUBLIC_URL`; the backend's `GRAPHDB_TIMEOUT_SECONDS` defaults to 10. These internal connection settings are distinct from the public Workbench address. The built frontend calls same-origin `/api`, which Caddy forwards to the backend. Only Caddy publishes host ports; GraphDB has no host port in this deployment.

Open `https://<app-host>` and authenticate with the app account. Load the bundled S1 example, preview its RDF, then choose *Save to GraphDB* and inspect the CQ1 team result. If S1's ID is already stored, the API returns `409`; use *Save as new scenario* to assign a fresh ID and save a separate graph. Record the returned scenario ID and graph IRI. Open the returned Workbench graph link at `https://<workbench-host>` with the separate operator account. On a fresh browser, Workbench may first require selecting repository `hi`; then use the returned named graph IRI to inspect the saved graph. After a planned container restart, revisit `https://<app-host>/api/scenarios/<scenario-id>/team` in the authenticated browser to check persistence. The application API schema is at `https://<app-host>/api/docs` behind app authentication.

These browser steps check the live HTTPS deployment manually. The automated Python and frontend tests use local services; the opt-in deployment test uses loopback HTTP. They do not verify real DNS, certificate issuance, or hosted HTTPS access.

## Storage, access, and updates

The development stack in [`compose.yaml`](../compose.yaml) starts only GraphDB, binds its unauthenticated port to `127.0.0.1:7200`, and uses `hi-project_graphdb-data`. The deployment stack uses `hi-project-deploy_graphdb-data` for GraphDB and separate `hi-project-deploy_caddy-data` and `hi-project-deploy_caddy-config` volumes for Caddy state. These are different Compose projects and volumes: development data does not appear in deployment automatically. Routine container restarts and Compose `down`/`up` retain named volumes; `down --volumes` removes them. Volumes are persistence, **not** a backup.

For an update, repeat the reviewed-revision checkout above and review any ontology/HINT changes before rebuilding:

```bash
docker compose --env-file .env.deploy -f compose.deploy.yaml up -d --build --wait
docker compose --env-file .env.deploy -f compose.deploy.yaml ps
```

Repeat the browser preview, save with a fresh ID, CQ1, and existing-scenario retrieval checks. Updating may briefly interrupt service. [Local GraphDB recovery](#local-graphdb-recovery-rehearsal) has been tested. Backing up and recovering the hosted research data still requires the separate production verification below.

To rotate either Caddy password, generate a replacement hash as above, update its `APP_AUTH_PASSWORD_HASH` or `WORKBENCH_AUTH_PASSWORD_HASH` value in `.env.deploy`, and recreate only the `web` service:

```bash
docker compose --env-file .env.deploy -f compose.deploy.yaml up -d --no-deps --force-recreate web
docker compose --env-file .env.deploy -f compose.deploy.yaml ps web
```

Check the new login at the affected HTTPS address and that the old password is rejected. Recreating `web` reads the changed environment without restarting `backend` or `graphdb`; a plain container restart would keep the old environment.

Caddy Basic Auth protects both the application (including `/api` write endpoints) and the separate Workbench hostname. It is shared-access protection, without per-researcher accounts or an audit trail. Give Workbench credentials only to trusted operators: GraphDB itself has no separate authentication in this stack, and a Workbench user can perform administrator-level reads and writes, including changes that bypass the API's create-only policy. Do not edit application graphs directly while researchers save. The backend must remain at **one worker and one instance**: its save lock is process-local, and GraphDB 10.8 read-committed transactions do not prevent concurrent independent writers from merging data. Multi-worker deployment needs a stronger coordination design.

## Local GraphDB recovery rehearsal

The [recovery Compose file](../compose.recovery.yaml) starts GraphDB 10.8.14 alone. Each project owns a separate named volume and Docker assigns a loopback port. The recovery CLI checks the local Docker socket, project role, container label, image, volume, port binding, and running Free edition. A restore requires an empty target. Use a fresh pair of project names for each rehearsal.

From the repository root in PowerShell with the [local Python environment](../README.md#local-setup-and-testing) installed, select the local Docker context. `desktop-linux` is the Docker Desktop Linux context on Windows. Run each block only after the preceding block succeeds.

```powershell
$context = 'desktop-linux'
$endpoint = docker --context $context context inspect $context --format '{{.Endpoints.docker.Host}}'
if ($LASTEXITCODE -ne 0 -or $endpoint -notmatch '^(npipe:////\./pipe/|unix:///)') { throw 'Use a local Docker socket context.' }
$id = [Guid]::NewGuid().ToString('N').Substring(0, 12)
$source = "hi-recovery-$id-source"
$target = "hi-recovery-$id-restore"
$bundle = Join-Path ([IO.Path]::GetTempPath()) "hi-recovery-$id-bundle"
$python = '.\.venv\Scripts\python.exe'

$volumes = docker --context $context volume ls --format '{{.Name}}'
if ($LASTEXITCODE -ne 0) { throw 'Could not list local volumes.' }
foreach ($project in @($source, $target)) {
    $containers = docker --context $context ps -aq --filter "label=com.docker.compose.project=$project"
    if ($LASTEXITCODE -ne 0 -or $containers -or $volumes -contains "${project}_graphdb-data") {
        throw 'Could not establish that the recovery project is fresh.'
    }
    docker --context $context compose -f compose.recovery.yaml -p $project up -d --wait --wait-timeout 180
    if ($LASTEXITCODE -ne 0) { throw 'GraphDB failed to start.' }
}
```

Seed the source with the checked-in reference graphs and S1–S7, plus one synthetic named graph and one default-context statement. Keep the source free of concurrent writers for the capture. The backup command creates a new bundle containing `hi.tar` and `manifest.json`. The manifest records the repository settings, explicit triple counts for every populated named graph and the default context, and the archive's SHA-256. Treat a failed command or a `.partial` file as an incomplete backup and retry with a new directory.

```powershell
& $python -m infra.recovery --context $context seed $source
if ($LASTEXITCODE -ne 0) { throw 'Seed failed.' }
& $python -m infra.recovery --context $context backup $source $bundle
if ($LASTEXITCODE -ne 0) { throw 'Backup failed.' }
& $python -m infra.recovery --context $context restore $target $bundle --canonical
if ($LASTEXITCODE -ne 0) { throw 'Restore or verification failed.' }
```

The restore checks the archive and SHA-256 before uploading it, then compares the recovered settings and populated graph inventory against the manifest. The stored default context is counted separately through RDF4J because GraphDB's SPARQL default can include named graph statements. `--canonical` also checks RDF equality up to blank-node renaming, SHACL, scenario identities, and CQ1 using the existing canonical verifier. Expect both references, all seven scenarios, the extra named graph with one triple, and one default-context triple. Run this before starting any backend or running `infra.graphdb setup`, which refreshes the reference graphs. To repeat just the checks, use `verify` in place of `restore`. Content changes that preserve counts in additional graphs require a separate RDF comparison.

For an application check, point standalone FastAPI at the verified restore. Use the rehearsal shell with the variables from above and close it after cleanup so the GraphDB URL stays scoped to the rehearsal.

```powershell
$binding = docker --context $context compose -f compose.recovery.yaml -p $target port graphdb 7200
if ($LASTEXITCODE -ne 0 -or $binding -notmatch '^127\.0\.0\.1:[1-9][0-9]*$') { throw 'Unexpected recovery binding.' }
$env:GRAPHDB_URL = "http://$binding"
$env:GRAPHDB_REPOSITORY = 'hi'
& $python -m uvicorn hi_scenario.api:app --host 127.0.0.1 --port 0
```

From another shell, enter the FastAPI port printed by Uvicorn and check that CQ1 returns each restored scenario's team and role labels.

```powershell
$apiPort = Read-Host 'Uvicorn loopback port'
foreach ($scenario in 1..7) {
    Invoke-RestMethod "http://127.0.0.1:$apiPort/scenarios/s$scenario/team" | ConvertTo-Json -Depth 8
}
```

Stop the test backend. In the rehearsal shell, remove only the two project names created for this run.

```powershell
docker --context $context compose -f compose.recovery.yaml -p $target down --volumes
docker --context $context compose -f compose.recovery.yaml -p $source down --volumes
```

The native archive covers repository `hi`. GraphDB system data, Caddy state, deployment secrets, and unsaved JSON drafts are outside its scope. Keep bundles outside the checkout in restricted storage. Use only archives from trusted operators.

### Checklist for the first Azure backup

- Obtain approval for the write pause, protected off-VM storage and custodians, retention, and acceptable time between backups. Decide whether Workbench system data needs separate preservation.
- Confirm the deployed image digest, version, edition, Git revision, and intended repository. During the pause, drain app, import, and direct Workbench writes. Capture the actual repository configuration and inventory, including noncanonical graphs and the default context.
- Use an operator-reviewed source command from inside the Azure GraphDB container for the repository-specific native backup. The local CLI is restricted to disposable Compose projects. Check archive completion and SHA-256, then transfer the archive and manifest to approved independent storage.
- Retrieve the off-VM copy and restore it on a separate, approved target. Compare it to the captured source before backend startup, then check CQ1 through the app. Record the results before relying on production recovery or proceeding with migration.

## Troubleshooting

Check service state and the relevant logs, without printing the environment file or a full rendered Compose configuration containing password hashes:

```bash
docker compose --env-file .env.deploy -f compose.deploy.yaml ps
docker compose --env-file .env.deploy -f compose.deploy.yaml logs --tail=100 web
docker compose --env-file .env.deploy -f compose.deploy.yaml logs --tail=100 backend
docker compose --env-file .env.deploy -f compose.deploy.yaml logs --tail=100 graphdb
```

If HTTPS is unavailable, check both DNS records, inbound ports 80/443, and `web` logs. A `503` from save or CQ1 means GraphDB or repository access is unavailable; check `graphdb` and `backend` logs. A `502` means the backend received an unexpected GraphDB result. Invalid scenario data returns `422`; a missing saved ID returns `404`. After a save timeout, query that ID before retrying because the write may have succeeded. If Workbench opens its repository picker instead of the graph, choose `hi` and reopen the graph link.
