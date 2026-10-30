// @vitest-environment jsdom
// Complete workflow: Svelte App → FastAPI → GraphDB → SPARQL (CQ1) → Svelte, with the real
// backend and the local Compose GraphDB (`docker compose up -d`, `python -m infra.graphdb setup`).
// Skipped when GraphDB is not reachable. Removes only the scenario graphs it created.
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';
import example from '../../examples/s1.json';
import { closedPort, startBackend } from './backend.js';

const GRAPHDB = (process.env.GRAPHDB_URL ?? 'http://127.0.0.1:7200').replace(/\/+$/, '');
const REPOSITORY = process.env.GRAPHDB_REPOSITORY ?? 'hi';
const graphdbReady = await fetch(`${GRAPHDB}/rest/repositories/${REPOSITORY}`)
  .then((response) => response.ok)
  .catch(() => false);
if (!graphdbReady) console.warn(`Skipping workflow tests: GraphDB repository '${REPOSITORY}' at ${GRAPHDB} is not reachable.`);

const RUN = `it-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
/** @type {Set<string>} */
const created = new Set();
/** @type {{ url: string, stop: () => void }[]} */
const backends = [];
let api = '';
let apiWithoutGraphDB = '';

/** @param {string} id */
const graphIri = (id) => `urn:hi-app:graph:scenario:${id}`;

/** @param {string} query */
async function select(query) {
  const response = await fetch(`${GRAPHDB}/repositories/${REPOSITORY}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', Accept: 'application/sparql-results+json' },
    body: new URLSearchParams({ query, infer: 'false' }),
  });
  expect(response.ok).toBe(true);
  return (await response.json()).results.bindings;
}

/** Number of triples stored in a scenario graph, read directly from GraphDB. @param {string} id */
async function storedTriples(id) {
  const rows = await select(`SELECT (COUNT(*) AS ?n) WHERE { GRAPH <${graphIri(id)}> { ?s ?p ?o } }`);
  return Number(rows[0].n.value);
}

/** @param {string} id @param {string} agent */
async function storedLabel(id, agent) {
  const rows = await select(
    `SELECT ?l WHERE { GRAPH <${graphIri(id)}> { <urn:hi-app:scenario:${id}:agent:${agent}> <http://www.w3.org/2000/01/rdf-schema#label> ?l } }`,
  );
  return rows.map((/** @type {any} */ row) => row.l.value);
}

beforeAll(async () => {
  if (!graphdbReady) return;
  backends.push(await startBackend());
  backends.push(await startBackend({ GRAPHDB_URL: `http://127.0.0.1:${await closedPort()}`, GRAPHDB_TIMEOUT_SECONDS: '2' }));
  [api, apiWithoutGraphDB] = backends.map((b) => b.url);
}, 60_000);

afterAll(async () => {
  backends.forEach((b) => b.stop());
  for (const id of created) {
    await fetch(`${GRAPHDB}/repositories/${REPOSITORY}/statements`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ update: `DROP SILENT GRAPH <${graphIri(id)}>` }),
    });
  }
});

/** @type {Record<string, any> | undefined} */
let app;
afterEach(() => {
  if (app) unmount(app);
  app = undefined;
  document.body.innerHTML = '';
  vi.unstubAllEnvs();
});

/** @param {string} apiUrl */
async function mountApp(apiUrl) {
  vi.stubEnv('VITE_API_URL', apiUrl);
  const { default: App } = await import('../src/App.svelte');
  app = mount(App, { target: document.body });
}

const text = () => (document.body.textContent ?? '').replace(/\s+/g, ' ');
/** @param {() => boolean} condition */
async function until(condition) {
  await vi.waitFor(() => {
    flushSync();
    if (!condition()) throw new Error(`condition not met: ${text().slice(-600)}`);
  }, { timeout: 20_000, interval: 50 });
}
/** @param {string} label */
function click(label) {
  const button = [...document.querySelectorAll('button')].find((b) => b.textContent?.trim() === label);
  if (!button) throw new Error(`No button "${label}"`);
  button.click();
  flushSync();
}
/** Load contract JSON through the form's "Open JSON file…" input. @param {object} data */
async function openJson(data) {
  const input = /** @type {HTMLInputElement} */ (document.querySelector('input[type=file]'));
  Object.defineProperty(input, 'files', { value: [new File([JSON.stringify(data)], 'scenario.json')], configurable: true });
  input.dispatchEvent(new Event('change', { bubbles: true }));
  await until(() => text().includes('Loaded scenario.json'));
}
/** The scenario ID currently in the form, from the JSON panel. */
const formId = () => JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}').id;
/** @param {string} id */
async function saveAndTrack(id) {
  created.add(id);
  click('Save to GraphDB');
  await until(() => text().includes('Saved in GraphDB') || text().includes('Not saved:') || text().includes('did not complete'));
}
const teamRows = () =>
  [...document.querySelectorAll('table.team tbody tr')].map((row) =>
    [...row.querySelectorAll('td')].map((cell) => cell.textContent?.replace(/\s+/g, ' ').trim()),
  );

/** @param {string} id @param {(data: any) => void} [change] */
function scenario(id, change) {
  const data = structuredClone(example);
  data.id = id;
  change?.(data);
  return data;
}

describe.skipIf(!graphdbReady)('Svelte → FastAPI → GraphDB → SPARQL → Svelte', () => {
  it('S1: preview, save, CQ1, and the Workbench link for the saved graph', async () => {
    const id = `${RUN}-s1`;
    await mountApp(api);
    await openJson(scenario(id));

    click('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    expect(text()).toContain('Not saved.');
    expect(await storedTriples(id)).toBe(0); // Previewing stores nothing.

    await saveAndTrack(id);
    expect(text()).toContain('Saved in GraphDB · repository hi · 43 triples');
    expect(text()).toContain(graphIri(id));
    expect(await storedTriples(id)).toBe(43);

    click('Show team composition (CQ1)');
    await until(() => text().includes('CQ1 over the saved graph'));
    expect(text()).toContain('2 members · Personal assistant HI system');
    expect(teamRows()).toEqual([
      ['AI assistant', 'Artificial Agent', 'System Assistant Role'],
      ['Human user', 'Human Agent', 'User Role'],
    ]);

    const link = /** @type {HTMLAnchorElement} */ (document.querySelector('a.button'));
    expect(link.href).toBe(`${GRAPHDB}/resource?uri=${encodeURIComponent(graphIri(id))}&role=context`);
    // Browsers request HTML and get the Workbench page (other Accept headers get RDF4J's 400).
    const page = await fetch(link.href, { headers: { Accept: 'text/html' } });
    expect(page.status).toBe(200);
    expect(page.headers.get('content-type')).toContain('text/html');
  }, 60_000);

  it('three agents: CQ1 lists every member with its own roles', async () => {
    const id = `${RUN}-three`;
    await mountApp(api);
    await openJson(scenario(id, (data) => {
      data.agents.push({ id: 'second-human', name: 'Clinician', kind: 'human', roles: ['HumanUserRole', 'ClinicianRole'] });
    }));
    await saveAndTrack(id);
    expect(text()).toContain('Saved in GraphDB · repository hi · 38 triples');
    click('Show team composition (CQ1)');
    await until(() => text().includes('3 members'));
    expect(teamRows()).toEqual([
      ['AI assistant', 'Artificial Agent', 'System Assistant Role'],
      ['Human user', 'Human Agent', 'User Role'],
      ['Clinician', 'Human Agent', 'Clinician Role, User Role'],
    ]);
  }, 60_000);

  it('edits after saving: no stale results, and saving creates a new scenario without touching the old one', async () => {
    const id = `${RUN}-edit`;
    await mountApp(api);
    await openJson(scenario(id));
    await saveAndTrack(id);
    expect(text()).toContain('Saved in GraphDB');
    click('Show team composition (CQ1)');
    await until(() => text().includes('2 members'));

    const name = /** @type {HTMLInputElement} */ (document.querySelector('#agent-human-user'));
    name.value = 'Renamed participant';
    name.dispatchEvent(new Event('input', { bubbles: true }));
    flushSync();
    expect(text()).not.toContain('Saved in GraphDB');
    expect(document.querySelector('table.team')).toBeNull();
    expect(document.querySelector('a.button')).toBeNull();
    expect(text()).toContain(`The form has changed since scenario ${id} was saved`);

    click('Save as new scenario');
    await until(() => text().includes('Saved in GraphDB'));
    const newId = formId();
    created.add(newId);
    expect(newId).not.toBe(id);
    expect(text()).toContain(graphIri(newId));
    expect(await storedLabel(newId, 'human-user')).toEqual(['Renamed participant']);
    expect(await storedLabel(id, 'human-user')).toEqual(['Human user']); // Original untouched.
    expect(await storedTriples(id)).toBe(43);
  }, 60_000);

  it('409: an existing ID is reported and never overwritten', async () => {
    const id = `${RUN}-conflict`;
    await mountApp(api);
    await openJson(scenario(id));
    await saveAndTrack(id);
    expect(text()).toContain('Saved in GraphDB');
    unmount(/** @type {any} */ (app));
    app = undefined;

    // A new page session with different content under the same ID.
    await mountApp(api);
    await openJson(scenario(id, (data) => { data.agents[0].name = 'Different person'; }));
    click('Save to GraphDB');
    await until(() => text().includes('Not saved: this scenario ID already exists in GraphDB.'));
    expect(text()).not.toContain('Saved in GraphDB');
    expect(await storedLabel(id, 'human-user')).toEqual(['Human user']);
    expect(await storedTriples(id)).toBe(43);
    expect(document.querySelector('.save button.primary')?.textContent?.trim()).toBe('Save as new scenario');
  }, 60_000);

  it('503: GraphDB unavailable is reported as not saved, while preview still works', async () => {
    const id = `${RUN}-down`;
    await mountApp(apiWithoutGraphDB);
    await openJson(scenario(id));
    click('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    click('Save to GraphDB');
    await until(() => text().includes('Not saved: GraphDB is unavailable.'));
    expect(text()).toContain('never overwritten');
    expect(text()).not.toContain('Saved in GraphDB');
    expect(await storedTriples(id)).toBe(0);
  }, 60_000);

  it('a failed CQ1 query does not undo a successful save', async () => {
    const id = `${RUN}-cq1-down`;
    await mountApp(api);
    await openJson(scenario(id));
    await saveAndTrack(id);
    expect(text()).toContain('Saved in GraphDB');
    vi.stubEnv('VITE_API_URL', apiWithoutGraphDB); // GraphDB becomes unreachable for the query.
    click('Show team composition (CQ1)');
    await until(() => text().includes('The team query failed. The scenario is still saved.'));
    expect(text()).toContain('GraphDB is unavailable');
    expect(text()).toContain('Saved in GraphDB');
    expect(await storedTriples(id)).toBe(43);
  }, 60_000);
});
