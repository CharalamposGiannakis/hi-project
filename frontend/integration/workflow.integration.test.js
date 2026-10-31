// @vitest-environment jsdom
// Complete workflow: Svelte App → FastAPI → GraphDB → SPARQL (CQ1) → Svelte, with the real
// backend and the local Compose GraphDB (`docker compose up -d`, `python -m infra.graphdb setup`).
// Skipped when GraphDB is not reachable. Removes only the scenario graphs it created.
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';
import example from '../../examples/s1.json';
import s2 from '../../examples/s2.json';
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

/** @param {string} query @returns {Promise<Record<string, { value: string }>[]>} */
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
  it('S2: previews, saves, and queries the complete reconstruction without merging entities', async () => {
    const id = `${RUN}-s2`;
    await mountApp(api);
    await openJson({ ...structuredClone(s2), id });
    click('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    expect(text()).toContain('195 triples · not saved');
    expect(await storedTriples(id)).toBe(0);
    await saveAndTrack(id);
    expect(text()).toContain('Saved in GraphDB · repository hi · 195 triples');
    expect(await storedTriples(id)).toBe(195);
    const base = `urn:hi-app:scenario:${id}:`;
    const requirements = await select(`
      SELECT ?task WHERE { GRAPH <${graphIri(id)}> {
        <${base}goal:safe-tool-retrieval> <https://w3id.org/hi-ontology#requiresTask> ?task
      } }
    `);
    expect(new Set(requirements.map((row) => row.task.value))).toEqual(new Set(s2.goal.required_tasks.map((task) => `${base}task:${task}`)));
    const types = await select(`SELECT ?entity ?type WHERE { GRAPH <${graphIri(id)}> { ?entity a ?type } }`);
    expect(types).toHaveLength(40);
    expect(types.filter((row) => row.type.value === 'https://w3id.org/hi-ontology#Task')).toHaveLength(10);
    const executions = await select(`
      PREFIX hi: <https://w3id.org/hi-ontology#>
      SELECT ?execution ?task ?evaluation ?experiment WHERE { GRAPH <${graphIri(id)}> {
        ?execution a hi:TaskExecution ; hi:realizesTask ?task ; hi:evaluatedBy ?evaluation .
        ?evaluation hi:hasExperiment ?experiment .
      } }
    `);
    expect(executions).toHaveLength(5);
    expect(new Set(executions.map((row) => row.evaluation.value)).size).toBe(5);
    expect(new Set(executions.map((row) => row.experiment.value)).size).toBe(5);
    expect(executions.filter((row) => row.task.value === `${base}task:heavy-lift`)).toHaveLength(2);
    expect(executions.some((row) => row.task.value === `${base}task:retrieve-tool`)).toBe(false);
    const participants = await select(`
      PREFIX hi: <https://w3id.org/hi-ontology#>
      SELECT ?participant ?execution WHERE { GRAPH <${graphIri(id)}> {
        <${base}interaction:explain-risk> hi:hasAgentInvolved ?participant .
        OPTIONAL { ?execution hi:hasInteractionEpisode <${base}interaction:explain-risk> }
      } }
    `);
    expect(participants).toHaveLength(2);
    expect(participants.every((row) => !row.execution)).toBe(true);
    click('Show team composition (CQ1)');
    await until(() => text().includes('CQ1 over the saved graph'));
    expect(teamRows().map((row) => row[0])).toEqual(['Human technician', 'Robot manipulator']);
  }, 60_000);

  it('S1: preview, save, CQ1, and the Workbench link for the saved graph', async () => {
    const id = `${RUN}-s1`;
    await mountApp(api);
    await openJson(scenario(id));

    click('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    expect(text()).toContain('Not saved.');
    expect(await storedTriples(id)).toBe(0); // Previewing stores nothing.

    await saveAndTrack(id);
    expect(text()).toContain('Saved in GraphDB · repository hi · 127 triples');
    expect(text()).toContain(graphIri(id));
    expect(await storedTriples(id)).toBe(127);

    const comments = await select(`
      SELECT ?entity ?description WHERE { GRAPH <${graphIri(id)}> {
        ?entity <http://www.w3.org/2000/01/rdf-schema#comment> ?description .
        FILTER(?entity = <urn:hi-app:scenario:${id}:goal:user-wellbeing> ||
          STRSTARTS(STR(?entity), 'urn:hi-app:scenario:${id}:task:'))
        FILTER(LANG(?description) = 'en')
      } }
    `);
    expect(comments.map((row) => [row.entity.value, row.description.value]).sort()).toEqual([
      [`urn:hi-app:scenario:${id}:goal:${example.goal.id}`, example.goal.description],
      ...example.tasks.map((task) => [`urn:hi-app:scenario:${id}:task:${task.id}`, task.description]),
    ].sort());

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

  it('persists only selected goal requirements while retaining every task and execution', async () => {
    const id = `${RUN}-goal-subset`;
    await mountApp(api);
    await openJson(scenario(id, (data) => { data.goal.required_tasks = ['data-collection']; }));
    await saveAndTrack(id);
    expect(text()).toContain('Saved in GraphDB · repository hi · 125 triples');
    expect(await storedTriples(id)).toBe(125);
    const required = await select(`
      SELECT ?task WHERE { GRAPH <${graphIri(id)}> {
        <urn:hi-app:scenario:${id}:goal:user-wellbeing> <https://w3id.org/hi-ontology#requiresTask> ?task
      } }
    `);
    expect(required.map((row) => row.task.value)).toEqual([`urn:hi-app:scenario:${id}:task:data-collection`]);
    const tasks = await select(`
      SELECT ?task WHERE { GRAPH <${graphIri(id)}> { ?task a <https://w3id.org/hi-ontology#Task> } }
    `);
    expect(new Set(tasks.map((row) => row.task.value))).toEqual(new Set(example.tasks.map((task) => `urn:hi-app:scenario:${id}:task:${task.id}`)));
    const executions = await select(`
      PREFIX hi: <https://w3id.org/hi-ontology#>
      SELECT ?execution WHERE { GRAPH <${graphIri(id)}> {
        ?execution hi:realizesTask <urn:hi-app:scenario:${id}:task:explanation> ;
          hi:towardsGoal <urn:hi-app:scenario:${id}:goal:user-wellbeing>
      } }
    `);
    expect(executions.map((row) => row.execution.value)).toEqual([`urn:hi-app:scenario:${id}:execution:explanation`]);
    click('Show team composition (CQ1)');
    await until(() => text().includes('CQ1 over the saved graph'));
    expect(teamRows()).toHaveLength(2);
  }, 60_000);

  it('stores one shared capability with explicit links to multiple agents and tasks', async () => {
    const id = `${RUN}-shared-capability`;
    await mountApp(api);
    await openJson(scenario(id, (data) => {
      delete data.executions; // Exercise the capability workflow without execution assignments.
      delete data.interactions;
      delete data.experiments;
      delete data.evaluations;
      data.agents.forEach((/** @type {import('../src/lib/scenario.js').Agent} */ agent) => { agent.name = 'Same display name'; });
      data.capabilities = [{
        id: 'shared', concept: 'ReasoningCapability',
        agents: ['human-user', 'ai-assistant'], tasks: ['data-collection', 'conflict-resolution'],
      }];
    }));
    await saveAndTrack(id);
    expect(await storedTriples(id)).toBe(55);
    const rows = await select(`
      PREFIX hi: <https://w3id.org/hi-ontology#>
      SELECT ?capability ?agent ?task WHERE { GRAPH <${graphIri(id)}> {
        ?capability a hi:Capability ; hi:hasCapabilityConcept <https://w3id.org/hi-thesaurus/ReasoningCapability> ; hi:allowsTask ?task .
        ?agent hi:hasCapability ?capability .
        ?task hi:requiresCapability ?capability .
      } }
    `);
    expect(rows).toHaveLength(4);
    expect(new Set(rows.map((row) => row.capability.value))).toEqual(new Set([`urn:hi-app:scenario:${id}:capability:shared`]));
    expect(new Set(rows.map((row) => row.agent.value))).toEqual(new Set([
      `urn:hi-app:scenario:${id}:agent:human-user`, `urn:hi-app:scenario:${id}:agent:ai-assistant`,
    ]));
    expect(new Set(rows.map((row) => row.task.value))).toEqual(new Set([
      `urn:hi-app:scenario:${id}:task:data-collection`, `urn:hi-app:scenario:${id}:task:conflict-resolution`,
    ]));
  }, 60_000);

  it('stores distinct executions for one task with explicit performers, goals, and optional methods', async () => {
    const id = `${RUN}-executions`;
    await mountApp(api);
    await openJson(scenario(id, (data) => {
      delete data.interactions;
      delete data.experiments;
      delete data.evaluations;
      data.executions = [
        { id: 'first', concept: 'DataCollectionTaskExecution', task: 'data-collection', agent: 'human-user', method: 'DataCollectionMethod' },
        { id: 'second', concept: 'DataCollectionTaskExecution', task: 'data-collection', agent: 'ai-assistant' },
        { id: 'repeat', concept: 'DataCollectionTaskExecution', task: 'data-collection', agent: 'human-user' },
      ];
    }));
    await saveAndTrack(id);
    expect(await storedTriples(id)).toBe(86);
    const rows = await select(`
      PREFIX hi: <https://w3id.org/hi-ontology#>
      SELECT ?execution ?agent ?task ?goal ?method WHERE { GRAPH <${graphIri(id)}> {
        ?execution a hi:TaskExecution ; hi:hasExecutionConcept <https://w3id.org/hi-thesaurus/DataCollectionTaskExecution> ;
          hi:realizesTask ?task ; hi:performedBy ?agent ; hi:towardsGoal ?goal .
        ?agent hi:performsExecution ?execution .
        OPTIONAL { ?execution hi:hasMethodConcept ?method }
      } }
    `);
    const base = `urn:hi-app:scenario:${id}:`;
    expect(rows).toHaveLength(3);
    expect(new Set(rows.map((row) => row.execution.value))).toEqual(new Set(['first', 'second', 'repeat'].map((name) => `${base}execution:${name}`)));
    expect(new Set(rows.map((row) => row.task.value))).toEqual(new Set([`${base}task:data-collection`]));
    expect(new Set(rows.map((row) => row.agent.value))).toEqual(new Set([`${base}agent:human-user`, `${base}agent:ai-assistant`]));
    expect(new Set(rows.map((row) => row.goal.value))).toEqual(new Set([`${base}goal:user-wellbeing`]));
    expect(rows.filter((row) => row.method)).toEqual([expect.objectContaining({
      execution: expect.objectContaining({ value: `${base}execution:first` }),
      method: expect.objectContaining({ value: 'https://w3id.org/hi-thesaurus/DataCollectionMethod' }),
    })]);
  }, 60_000);

  it('persists shared evaluations, multiple metrics, descriptions, and tagged hypotheses', async () => {
    const id = `${RUN}-assessment`;
    await mountApp(api);
    await openJson(scenario(id, (data) => {
      const metrics = ['FairOutcomeMetric', 'UndueInfluenceMetric', 'ExplanationClarityMetric'];
      data.experiments = [{
        ...data.experiments[0], id: 'shared', concept: 'DeliberationSupportExperiment', metrics,
        hypothesis_language: 'en', description: 'Shared experiment description.',
      }];
      data.evaluations = [{
        id: 'shared', concept: 'AIInterventionImpactEvaluation', metrics, experiment: 'shared',
        executions: data.executions.map((/** @type {{ id: string }} */ e) => e.id), description: 'Shared evaluation description.',
      }];
    }));
    await saveAndTrack(id);
    expect(await storedTriples(id)).toBe(112);
    const base = `urn:hi-app:scenario:${id}:`;
    const rows = await select(`
      PREFIX hi: <https://w3id.org/hi-ontology#>
      SELECT ?execution ?evaluation ?experiment ?metric WHERE { GRAPH <${graphIri(id)}> {
        ?execution hi:evaluatedBy ?evaluation .
        ?evaluation a hi:Evaluation ; hi:hasEvaluationConcept <https://w3id.org/hi-thesaurus/AIInterventionImpactEvaluation> ;
          hi:hasExperiment ?experiment ; hi:hasMetricConcept ?metric .
        ?experiment a hi:Experiment ; hi:hasMetricTested ?metric .
      } }
    `);
    expect(rows).toHaveLength(9);
    expect(new Set(rows.map((row) => row.evaluation.value))).toEqual(new Set([`${base}evaluation:shared`]));
    expect(new Set(rows.map((row) => row.experiment.value))).toEqual(new Set([`${base}experiment:shared`]));
    expect(new Set(rows.map((row) => row.execution.value))).toEqual(new Set(example.executions.map((e) => `${base}execution:${e.id}`)));
    const literals = await select(`
      PREFIX hi: <https://w3id.org/hi-ontology#>
      PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
      SELECT ?null ?alternative ?experimentDescription ?evaluationDescription WHERE { GRAPH <${graphIri(id)}> {
        <${base}experiment:shared> hi:hasNullHypothesis ?null ; hi:hasAlternativeHypothesis ?alternative ; rdfs:comment ?experimentDescription .
        <${base}evaluation:shared> rdfs:comment ?evaluationDescription .
      } }
    `);
    expect(literals).toHaveLength(1);
    expect(literals[0].null).toMatchObject({ value: example.experiments[0].null_hypothesis, 'xml:lang': 'en' });
    expect(literals[0].alternative).toMatchObject({ 'xml:lang': 'en' });
    expect(literals[0].evaluationDescription.value).toBe('Shared evaluation description.');
  }, 60_000);

  it('persists multiple interactions, three participants, and many-to-many execution links', async () => {
    const id = `${RUN}-interactions`;
    await mountApp(api);
    await openJson(scenario(id, (data) => {
      data.agents.push({ ...data.agents[0], id: 'second-human' });
      data.interactions = [
        { id: 'shared', intent: 'ExplanationIntent', modality: 'VerbalDialogueModality', agents: ['ai-assistant', 'human-user', 'second-human'], executions: ['explanation', 'conflict-resolution'], description: 'Shared English description.' },
        { id: 'unlinked', intent: 'DeliberationIntent', modality: 'TextChatModality', agents: ['ai-assistant', 'human-user'], executions: [] },
        { id: 'also-shared', intent: 'ExplanationIntent', modality: 'VerbalDialogueModality', agents: ['ai-assistant', 'human-user'], executions: ['explanation'] },
      ];
    }));
    await saveAndTrack(id);
    expect(await storedTriples(id)).toBe(146);
    const base = `urn:hi-app:scenario:${id}:`;
    const rows = await select(`
      PREFIX hi: <https://w3id.org/hi-ontology#>
      PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
      SELECT ?interaction ?agent ?intent ?modality ?execution ?description WHERE { GRAPH <${graphIri(id)}> {
        ?interaction a hi:Interaction ; hi:hasAgentInvolved ?agent ;
          hi:hasInteractionIntentConcept ?intent ; hi:hasInteractionModalityConcept ?modality .
        OPTIONAL { ?execution hi:hasInteractionEpisode ?interaction }
        OPTIONAL { ?interaction rdfs:comment ?description }
      } }
    `);
    expect(rows).toHaveLength(10);
    expect(new Set(rows.map((row) => row.interaction.value))).toEqual(new Set(['shared', 'unlinked', 'also-shared'].map((name) => `${base}interaction:${name}`)));
    const shared = rows.filter((row) => row.interaction.value === `${base}interaction:shared`);
    expect(shared).toHaveLength(6);
    expect(new Set(shared.map((row) => row.agent.value))).toEqual(new Set(['ai-assistant', 'human-user', 'second-human'].map((name) => `${base}agent:${name}`)));
    expect(shared[0].intent.value).toBe('https://w3id.org/hi-thesaurus/ExplanationIntent');
    expect(shared[0].description).toMatchObject({ value: 'Shared English description.', 'xml:lang': 'en' });
    expect(rows.filter((row) => row.interaction.value === `${base}interaction:unlinked`).every((row) => !row.execution)).toBe(true);
    expect(new Set(rows.filter((row) => row.execution?.value === `${base}execution:explanation`).map((row) => row.interaction.value))).toEqual(new Set([`${base}interaction:shared`, `${base}interaction:also-shared`]));
  }, 60_000);

  it('three agents: CQ1 lists every member with its own roles', async () => {
    const id = `${RUN}-three`;
    await mountApp(api);
    await openJson(scenario(id, (data) => {
      data.agents.push({ id: 'second-human', name: 'Clinician', kind: 'human', roles: ['HumanUserRole', 'ClinicianRole'] });
    }));
    await saveAndTrack(id);
    expect(text()).toContain('Saved in GraphDB · repository hi · 133 triples');
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
    expect(await storedTriples(id)).toBe(127);
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
    expect(await storedTriples(id)).toBe(127);
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
    expect(await storedTriples(id)).toBe(127);
  }, 60_000);
});
