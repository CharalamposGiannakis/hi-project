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

Repeat the browser preview, save with a fresh ID, CQ1, and existing-scenario retrieval checks. Updating may briefly interrupt service; no zero-downtime or migration process is provided. **A verified backup-and-restore procedure has not yet been established.** Establish and test one before treating this as durable research storage; this guide makes no recovery guarantee.

To rotate either Caddy password, generate a replacement hash as above, update its `APP_AUTH_PASSWORD_HASH` or `WORKBENCH_AUTH_PASSWORD_HASH` value in `.env.deploy`, and recreate only the `web` service:

```bash
docker compose --env-file .env.deploy -f compose.deploy.yaml up -d --no-deps --force-recreate web
docker compose --env-file .env.deploy -f compose.deploy.yaml ps web
```

Check the new login at the affected HTTPS address and that the old password is rejected. Recreating `web` reads the changed environment without restarting `backend` or `graphdb`; a plain container restart would keep the old environment.

Caddy Basic Auth protects both the application (including `/api` write endpoints) and the separate Workbench hostname. It is shared-access protection, without per-researcher accounts or an audit trail. Give Workbench credentials only to trusted operators: GraphDB itself has no separate authentication in this stack, and a Workbench user can perform administrator-level reads and writes, including changes that bypass the API's create-only policy. Do not edit application graphs directly while researchers save. The backend must remain at **one worker and one instance**: its save lock is process-local, and GraphDB 10.8 read-committed transactions do not prevent concurrent independent writers from merging data. Multi-worker deployment needs a stronger coordination design.

## Troubleshooting

Check service state and the relevant logs, without printing the environment file or a full rendered Compose configuration containing password hashes:

```bash
docker compose --env-file .env.deploy -f compose.deploy.yaml ps
docker compose --env-file .env.deploy -f compose.deploy.yaml logs --tail=100 web
docker compose --env-file .env.deploy -f compose.deploy.yaml logs --tail=100 backend
docker compose --env-file .env.deploy -f compose.deploy.yaml logs --tail=100 graphdb
```

If HTTPS is unavailable, check both DNS records, inbound ports 80/443, and `web` logs. A `503` from save or CQ1 means GraphDB or repository access is unavailable; check `graphdb` and `backend` logs. A `502` means the backend received an unexpected GraphDB result. Invalid scenario data returns `422`; a missing saved ID returns `404`. After a save timeout, query that ID before retrying because the write may have succeeded. If Workbench opens its repository picker instead of the graph, choose `hi` and reopen the graph link.
