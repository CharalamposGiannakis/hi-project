// Persistence and exploration through the API client against local GraphDB.
// Skipped when GraphDB is not reachable. Removes only the scenario graphs it created.
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import example from '../../examples/s1.json';
import s2 from '../../examples/s2.json';
import s3 from '../../examples/s3.json';
import s4 from '../../examples/s4.json';
import s5 from '../../examples/s5.json';
import s6 from '../../examples/s6.json';
import s7 from '../../examples/s7.json';
import { fetchExplorerCatalog, fetchTeam, requestConceptExploration, requestExplorerQuery, requestPreview, saveScenario } from '../src/lib/api.js';
import { closedPort, startBackend } from './backend.js';

const GRAPHDB = (process.env.GRAPHDB_URL ?? 'http://127.0.0.1:7200').replace(/\/+$/, '');
const REPOSITORY = process.env.GRAPHDB_REPOSITORY ?? 'hi';
const graphdbReady = await fetch(`${GRAPHDB}/rest/repositories/${REPOSITORY}`, { signal: AbortSignal.timeout(5_000) })
  .then((response) => response.ok)
  .catch(() => false);
if (!graphdbReady) {
  const message = `GraphDB repository '${REPOSITORY}' at ${GRAPHDB} is not reachable.`;
  if (process.env.HI_GRAPHDB_LIVE === '1') throw new Error(message);
  console.warn(`Skipping workflow tests: ${message}`);
}

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
  backends.push(await startBackend({ GRAPHDB_APPROVED_SCENARIO_IDS: '' }));
  backends.push(await startBackend({ GRAPHDB_URL: `http://127.0.0.1:${await closedPort()}`, GRAPHDB_TIMEOUT_SECONDS: '2' }));
  [api, apiWithoutGraphDB] = backends.map((b) => b.url);
}, 60_000);

afterAll(async () => {
  backends.forEach((b) => b.stop());
  for (const id of created) {
    const response = await fetch(`${GRAPHDB}/repositories/${REPOSITORY}/statements`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ update: `DROP SILENT GRAPH <${graphIri(id)}>` }),
    });
    expect(response.ok).toBe(true);
    expect(await storedTriples(id)).toBe(0);
  }
});

/**
 * @param {{ id: string }} data
 * @param {number} [triples]
 */
async function saveAndTrack(data, triples) {
  const result = await saveScenario(data, { baseUrl: api });
  if (result.kind !== 'ok') throw new Error(JSON.stringify(result));
  created.add(data.id);
  expect(result.saved).toMatchObject({
    scenario_id: data.id, repository_id: REPOSITORY, graph_iri: graphIri(data.id),
  });
  if (triples !== undefined) expect(result.saved.triple_count).toBe(triples);
  return result.saved;
}

/** @param {string} id */
async function readTeam(id) {
  const result = await fetchTeam(id, { baseUrl: api });
  if (result.kind !== 'ok') throw new Error(JSON.stringify(result));
  expect(result.team.scenario_id).toBe(id);
  return result.team;
}

/** @param {import('../src/lib/api.js').TeamComposition} team */
function teamRows(team) {
  return team.members.map((member) => [
    member.name, member.types.map((type) => type.label).join(', '),
    member.roles.map((role) => role.label).join(', '),
  ]);
}

/** @param {string} id @param {(data: any) => void} [change] */
function scenario(id, change) {
  const data = structuredClone(example);
  data.id = id;
  change?.(data);
  return data;
}

describe.skipIf(!graphdbReady)('API client → FastAPI → GraphDB → SPARQL', () => {
  it('queries validated session snapshots with shared knowledge and compares session scenarios', async () => {
    const options = { baseUrl: api };
    const uploads = [
      { id: 'first-file', file_name: 'first.json', scenario: scenario('s1', (data) => { data.agents[0].name = 'First uploaded member'; }) },
      { id: 'second-file', file_name: 'second.json', scenario: scenario('s1', (data) => { data.agents[0].name = 'Second uploaded member'; }) },
      { id: 'builder-snapshot', file_name: 'Builder · S1', scenario: scenario('s1', (data) => { data.agents[0].name = 'Validated Builder member'; }) },
    ];
    for (const upload of uploads) {
      expect(await requestPreview(upload.scenario, options)).toMatchObject({ kind: 'ok' });
    }
    const catalog = await fetchExplorerCatalog(options);
    if (catalog.kind !== 'ok') throw new Error(JSON.stringify(catalog));
    expect(catalog.data.questions.map((question) => question.id))
      .toEqual(Array.from({ length: 12 }, (_, index) => `cq${index + 1}`));
    expect(catalog.data.questions.filter((question) => question.status === 'scientific_review_pending').map((question) => question.id))
      .toEqual(['cq3', 'cq4', 'cq12']);

    const answer = await requestExplorerQuery({
      question_id: 'cq1', scope: 'combined', uploads, shared_scenario_id: 's1',
    }, options);
    if (answer.kind !== 'ok') throw new Error(JSON.stringify(answer));
    expect(new Set(answer.data.sources.map((source) => source.id)))
      .toEqual(new Set(['upload:first-file', 'upload:second-file', 'upload:builder-snapshot', 'reference:s1']));
    expect(new Set(answer.data.sources.map((source) => source.graph_iri)).size).toBe(4);
    for (const [member, sourceId] of [
      ['First uploaded member', 'upload:first-file'], ['Second uploaded member', 'upload:second-file'],
      ['Validated Builder member', 'upload:builder-snapshot'], ['Human user', 'reference:s1'],
    ]) {
      expect(answer.data.rows).toEqual(expect.arrayContaining([
        expect.objectContaining({ source_id: sourceId, values: expect.objectContaining({ member }) }),
      ]));
    }

    const searched = await requestConceptExploration({
      scope: 'session', uploads, category: 'Constraint', concept: 'PrivacyConstraint',
    }, options);
    if (searched.kind !== 'ok') throw new Error(JSON.stringify(searched));
    expect(new Set(searched.data.rows.map((row) => row.source_id))).toEqual(new Set(['upload:first-file', 'upload:second-file', 'upload:builder-snapshot']));
    const comparison = await requestConceptExploration({
      scope: 'combined', uploads: [uploads[0]], shared_scenario_id: 's5', compare: true,
      comparison_source_ids: ['upload:first-file', 'reference:s5'],
    }, options);
    if (comparison.kind !== 'ok') throw new Error(JSON.stringify(comparison));
    expect(new Set(comparison.data.sources.map((source) => source.id))).toEqual(new Set(['upload:first-file', 'reference:s5']));
    expect(new Set(comparison.data.rows.map((row) => row.values.overlap))).toEqual(new Set([
      'Recorded in both', 'Recorded only in first scenario', 'Recorded only in second scenario',
    ]));
    for (const response of [answer.data, searched.data, comparison.data]) {
      for (const source of response.sources) {
        expect(await select(`SELECT ?s WHERE { GRAPH <${source.graph_iri}> { ?s ?p ?o } } LIMIT 1`)).toEqual([]);
      }
    }
  }, 30_000);

  it('finds shared concepts and compares an added snapshot with S5 without publishing', async () => {
    const options = { baseUrl: api };
    const found = await requestConceptExploration({
      scope: 'shared', category: 'Capability', concept: 'KnowledgeGraphQueryingCapability',
    }, options);
    if (found.kind !== 'ok') throw new Error(JSON.stringify(found));
    expect(new Set(found.data.rows.map((row) => row.source_id)))
      .toEqual(new Set(['s2', 's4', 's5', 's6', 's7'].map((id) => `reference:${id}`)));

    const privacy = await requestConceptExploration({
      scope: 'shared', category: 'Constraint', concept: 'PrivacyConstraint',
    }, options);
    if (privacy.kind !== 'ok') throw new Error(JSON.stringify(privacy));
    expect(new Set(privacy.data.rows.map((row) => row.source_id)))
      .toEqual(new Set(['s1', 's4', 's5', 's7'].map((id) => `reference:${id}`)));
    expect(new Set(privacy.data.rows.map((row) => row.values.connection)))
      .toEqual(new Set(['Team constraint', 'Context constraint']));

    const comparison = await requestConceptExploration({
      scope: 'combined', uploads: [{ id: 'builder-s5', file_name: 'Builder · S5', scenario: scenario('s5') }],
      shared_scenario_id: 's5', compare: true, comparison_source_ids: ['upload:builder-s5', 'reference:s5'],
    }, options);
    if (comparison.kind !== 'ok') throw new Error(JSON.stringify(comparison));
    expect(new Set(comparison.data.sources.map((source) => source.id))).toEqual(new Set(['upload:builder-s5', 'reference:s5']));
    expect(new Set(comparison.data.rows.map((row) => row.values.overlap)))
      .toEqual(new Set(['Recorded in both', 'Recorded only in first scenario', 'Recorded only in second scenario']));
    expect(comparison.data.truncated).toBe(false);
    expect(comparison.data.rows.every((row) => row.evidence.length > 0)).toBe(true);
    for (const source of comparison.data.sources) {
      expect(await select(`SELECT ?s WHERE { GRAPH <${source.graph_iri}> { ?s ?p ?o } } LIMIT 1`)).toEqual([]);
    }
  }, 30_000);

  it('explores an added snapshot alongside an approved named graph and rolls back the snapshot', async () => {
    const id = `${RUN}-explorer`;
    await saveAndTrack(scenario(id, (data) => { data.agents[0].name = 'Published fixture member'; }));
    const explorer = await startBackend({ GRAPHDB_APPROVED_SCENARIO_IDS: id });
    backends.push(explorer);
    const options = { baseUrl: explorer.url };
    expect(await fetchExplorerCatalog(options)).toMatchObject({
      kind: 'ok', data: { shared_source: 'approved', scenarios: [{ scenario_id: id }] },
    });

    const draft = scenario(id, (data) => { data.agents[0].name = 'Private draft fixture member'; });
    const answer = await requestExplorerQuery({
      question_id: 'cq1', scope: 'combined', shared_scenario_id: id,
      uploads: [{ id: 'builder-approved', file_name: 'Builder snapshot', scenario: draft }],
    }, options);
    expect(answer.kind).toBe('ok');
    if (answer.kind !== 'ok') throw new Error(JSON.stringify(answer));
    expect(answer.data.rows).toEqual(expect.arrayContaining([
      expect.objectContaining({ source_id: `approved:${id}`, values: expect.objectContaining({ member: 'Published fixture member' }) }),
      expect.objectContaining({ source_id: 'upload:builder-approved', values: expect.objectContaining({ member: 'Private draft fixture member' }) }),
    ]));
    const provisional = answer.data.sources.find((source) => source.publication_status === 'provisional');
    if (!provisional) throw new Error('Missing provisional source');
    expect(await select(`SELECT ?s WHERE { GRAPH <${provisional.graph_iri}> { ?s ?p ?o } } LIMIT 1`)).toEqual([]);
    expect(await storedLabel(id, draft.agents[0].id)).toEqual(['Published fixture member']);
  }, 30_000);

  it('S7: saves 29 identities, separate Team/Context constraints, seven evaluation links, and both episodes', async () => {
    const id = `${RUN}-s7`;
    const data = { ...structuredClone(s7), id };
    expect(await requestPreview(data, { baseUrl: api })).toMatchObject({
      kind: 'ok', preview: { triple_count: 173 },
    });
    expect(await storedTriples(id)).toBe(0);
    await saveAndTrack(data, 173);
    expect(await storedTriples(id)).toBe(173);
    const base = `urn:hi-app:scenario:${id}:`;
    const typed = await select(`SELECT ?entity WHERE { GRAPH <${graphIri(id)}> { ?entity a ?type } }`);
    const expected = [
      'team', 'context', `use-case:${s7.use_case.id}`, `goal:${s7.goal.id}`,
      ...s7.agents.map((agent) => `agent:${agent.id}`), ...s7.tasks.map((task) => `task:${task.id}`),
      ...s7.capabilities.map((capability) => `capability:${capability.id}`), ...s7.executions.map((execution) => `execution:${execution.id}`),
      ...s7.experiments.map((experiment) => `experiment:${experiment.id}`), ...s7.evaluations.map((evaluation) => `evaluation:${evaluation.id}`),
      ...s7.interactions.map((interaction) => `interaction:${interaction.id}`),
    ];
    expect(typed).toHaveLength(29);
    expect(new Set(typed.map((row) => row.entity.value))).toEqual(new Set(expected.map((entity) => base + entity)));
    const constraints = await select(`
      PREFIX hi: <https://w3id.org/hi-ontology#>
      SELECT ?subject ?constraint WHERE { GRAPH <${graphIri(id)}> { ?subject hi:hasConstraintConcept ?constraint } }
    `);
    expect(constraints).toHaveLength(6);
    for (const subject of ['team', 'context']) {
      expect(new Set(constraints.filter((row) => row.subject.value === base + subject).map((row) => row.constraint.value)))
        .toEqual(new Set(s7.team_constraints.map((constraint) => `https://w3id.org/hi-thesaurus/${constraint}`)));
    }
    const evaluated = await select(`
      PREFIX hi: <https://w3id.org/hi-ontology#>
      SELECT ?execution ?evaluation WHERE { GRAPH <${graphIri(id)}> { ?execution hi:evaluatedBy ?evaluation } }
    `);
    expect(evaluated).toHaveLength(7);
    expect(new Set(evaluated.map((row) => row.execution.value))).toEqual(new Set(s7.executions.map((execution) => `${base}execution:${execution.id}`)));
    expect(new Set(evaluated.map((row) => row.evaluation.value))).toEqual(new Set([`${base}evaluation:vr-guide-impact`]));
    const episodes = await select(`
      PREFIX hi: <https://w3id.org/hi-ontology#>
      SELECT ?execution ?interaction WHERE { GRAPH <${graphIri(id)}> { ?execution hi:hasInteractionEpisode ?interaction } }
    `);
    expect(episodes).toHaveLength(2);
    expect(episodes.map((row) => [row.execution.value, row.interaction.value])).toEqual(expect.arrayContaining([
      [`${base}execution:recommend-artifacts`, `${base}interaction:vr-guided-tour`],
      [`${base}execution:answer-questions`, `${base}interaction:qa`],
    ]));
    const team = await readTeam(id);
    expect(teamRows(team)).toHaveLength(2);
    expect(new Set(teamRows(team).map((row) => row[0]))).toEqual(new Set(s7.agents.map((agent) => agent.name)));
  }, 60_000);

  it('S6: saves shared Explanation, six evaluation links, and distinct episodes without linking the human explanation', async () => {
    const id = `${RUN}-s6`;
    const data = { ...structuredClone(s6), id };
    expect(await requestPreview(data, { baseUrl: api })).toMatchObject({
      kind: 'ok', preview: { triple_count: 150 },
    });
    expect(await storedTriples(id)).toBe(0);
    await saveAndTrack(data, 150);
    expect(await storedTriples(id)).toBe(150);
    const base = `urn:hi-app:scenario:${id}:`;
    const typed = await select(`SELECT ?entity WHERE { GRAPH <${graphIri(id)}> { ?entity a ?type } }`);
    const expected = [
      'team', 'context', `use-case:${s6.use_case.id}`, `goal:${s6.goal.id}`,
      ...s6.agents.map((agent) => `agent:${agent.id}`), ...s6.tasks.map((task) => `task:${task.id}`),
      ...s6.capabilities.map((capability) => `capability:${capability.id}`), ...s6.executions.map((execution) => `execution:${execution.id}`),
      ...s6.experiments.map((experiment) => `experiment:${experiment.id}`), ...s6.evaluations.map((evaluation) => `evaluation:${evaluation.id}`),
      ...s6.interactions.map((interaction) => `interaction:${interaction.id}`),
    ];
    expect(typed).toHaveLength(26);
    expect(new Set(typed.map((row) => row.entity.value))).toEqual(new Set(expected.map((entity) => base + entity)));
    const shared = await select(`
      PREFIX hi: <https://w3id.org/hi-ontology#>
      SELECT ?agent ?capability WHERE { GRAPH <${graphIri(id)}> {
        ?agent hi:hasCapability ?capability .
        ?capability hi:hasCapabilityConcept <https://w3id.org/hi-thesaurus/ExplainingCapability> .
      } }
    `);
    expect(shared).toHaveLength(2);
    expect(new Set(shared.map((row) => row.capability.value))).toEqual(new Set([`${base}capability:explaining`]));
    expect(new Set(shared.map((row) => row.agent.value))).toEqual(new Set(s6.agents.map((agent) => `${base}agent:${agent.id}`)));
    const evaluated = await select(`
      PREFIX hi: <https://w3id.org/hi-ontology#>
      SELECT ?execution ?evaluation WHERE { GRAPH <${graphIri(id)}> { ?execution hi:evaluatedBy ?evaluation } }
    `);
    expect(evaluated).toHaveLength(6);
    expect(new Set(evaluated.map((row) => row.execution.value))).toEqual(new Set(s6.executions.map((execution) => `${base}execution:${execution.id}`)));
    expect(new Set(evaluated.map((row) => row.evaluation.value))).toEqual(new Set([`${base}evaluation:negotiation-impact`]));
    const episodes = await select(`
      PREFIX hi: <https://w3id.org/hi-ontology#>
      SELECT ?execution ?interaction WHERE { GRAPH <${graphIri(id)}> { ?execution hi:hasInteractionEpisode ?interaction } }
    `);
    expect(episodes).toHaveLength(2);
    expect(episodes.map((row) => [row.execution.value, row.interaction.value])).toEqual(expect.arrayContaining([
      [`${base}execution:negotiate`, `${base}interaction:negotiation`],
      [`${base}execution:explain-decision`, `${base}interaction:explain-allocation`],
    ]));
    expect(episodes.some((row) => row.execution.value === `${base}execution:explain-operator`)).toBe(false);
    const team = await readTeam(id);
    expect(teamRows(team)).toHaveLength(2);
    expect(new Set(teamRows(team).map((row) => row[0]))).toEqual(new Set(s6.agents.map((agent) => agent.name)));
  }, 60_000);

  it('S5: saves all identities, shared Explanation capability, separate evaluation groups, and two dialogue episodes', async () => {
    const id = `${RUN}-s5`;
    const data = { ...structuredClone(s5), id };
    expect(await requestPreview(data, { baseUrl: api })).toMatchObject({
      kind: 'ok', preview: { triple_count: 139 },
    });
    expect(await storedTriples(id)).toBe(0);
    await saveAndTrack(data, 139);
    expect(await storedTriples(id)).toBe(139);
    const base = `urn:hi-app:scenario:${id}:`;
    const typed = await select(`SELECT ?entity WHERE { GRAPH <${graphIri(id)}> { ?entity a ?type } }`);
    const expected = [
      'team', 'context', `use-case:${s5.use_case.id}`, `goal:${s5.goal.id}`,
      ...s5.agents.map((agent) => `agent:${agent.id}`), ...s5.tasks.map((task) => `task:${task.id}`),
      ...s5.capabilities.map((capability) => `capability:${capability.id}`), ...s5.executions.map((execution) => `execution:${execution.id}`),
      ...s5.experiments.map((experiment) => `experiment:${experiment.id}`), ...s5.evaluations.map((evaluation) => `evaluation:${evaluation.id}`),
      ...s5.interactions.map((interaction) => `interaction:${interaction.id}`),
    ];
    expect(typed).toHaveLength(24);
    expect(new Set(typed.map((row) => row.entity.value))).toEqual(new Set(expected.map((entity) => base + entity)));
    const shared = await select(`
      PREFIX hi: <https://w3id.org/hi-ontology#>
      SELECT ?agent WHERE { GRAPH <${graphIri(id)}> { ?agent hi:hasCapability <${base}capability:explaining> } }
    `);
    expect(new Set(shared.map((row) => row.agent.value))).toEqual(new Set(s5.agents.map((agent) => `${base}agent:${agent.id}`)));
    const evaluations = await select(`
      PREFIX hi: <https://w3id.org/hi-ontology#>
      SELECT ?execution ?evaluation ?experiment WHERE { GRAPH <${graphIri(id)}> {
        ?execution hi:evaluatedBy ?evaluation . ?evaluation hi:hasExperiment ?experiment .
      } }
    `);
    expect(evaluations).toHaveLength(5);
    for (const evaluation of s5.evaluations) {
      const rows = evaluations.filter((row) => row.evaluation.value === `${base}evaluation:${evaluation.id}`);
      expect(new Set(rows.map((row) => row.execution.value))).toEqual(new Set(evaluation.executions.map((execution) => `${base}execution:${execution}`)));
      expect(new Set(rows.map((row) => row.experiment.value))).toEqual(new Set([`${base}experiment:${evaluation.experiment}`]));
    }
    const episodes = await select(`
      PREFIX hi: <https://w3id.org/hi-ontology#>
      SELECT ?execution ?interaction WHERE { GRAPH <${graphIri(id)}> { ?execution hi:hasInteractionEpisode ?interaction } }
    `);
    expect(episodes).toHaveLength(2);
    expect(new Set(episodes.map((row) => row.execution.value))).toEqual(new Set([`${base}execution:explain-ai`, `${base}execution:explain-human`]));
    expect(new Set(episodes.map((row) => row.interaction.value))).toEqual(new Set([`${base}interaction:clinical-dialogue`]));
    const team = await readTeam(id);
    expect(teamRows(team)).toHaveLength(2);
    expect(new Set(teamRows(team).map((row) => row[0]))).toEqual(new Set(s5.agents.map((agent) => agent.name)));
  }, 60_000);

  it('S4: saves all 26 identities, six evaluation links, and the specific explanation interaction', async () => {
    const id = `${RUN}-s4`;
    const data = { ...structuredClone(s4), id };
    expect(await requestPreview(data, { baseUrl: api })).toMatchObject({
      kind: 'ok', preview: { triple_count: 154 },
    });
    expect(await storedTriples(id)).toBe(0);
    await saveAndTrack(data, 154);
    expect(await storedTriples(id)).toBe(154);
    const base = `urn:hi-app:scenario:${id}:`;
    const typed = await select(`SELECT ?entity WHERE { GRAPH <${graphIri(id)}> { ?entity a ?type } }`);
    const expected = [
      'team', 'context', `use-case:${s4.use_case.id}`, `goal:${s4.goal.id}`,
      ...s4.agents.map((agent) => `agent:${agent.id}`), ...s4.tasks.map((task) => `task:${task.id}`),
      ...s4.capabilities.map((capability) => `capability:${capability.id}`), ...s4.executions.map((execution) => `execution:${execution.id}`),
      ...s4.experiments.map((experiment) => `experiment:${experiment.id}`), ...s4.evaluations.map((evaluation) => `evaluation:${evaluation.id}`),
      ...s4.interactions.map((interaction) => `interaction:${interaction.id}`),
    ];
    expect(typed).toHaveLength(26);
    expect(new Set(typed.map((row) => row.entity.value))).toEqual(new Set(expected.map((entity) => base + entity)));
    const evaluations = await select(`
      PREFIX hi: <https://w3id.org/hi-ontology#>
      SELECT ?execution ?evaluation WHERE { GRAPH <${graphIri(id)}> { ?execution hi:evaluatedBy ?evaluation } }
    `);
    expect(evaluations).toHaveLength(6);
    expect(new Set(evaluations.map((row) => row.execution.value))).toEqual(new Set(s4.executions.map((execution) => `${base}execution:${execution.id}`)));
    expect(new Set(evaluations.map((row) => row.evaluation.value))).toEqual(new Set([`${base}evaluation:tutor-impact`]));
    const episodes = await select(`
      PREFIX hi: <https://w3id.org/hi-ontology#>
      SELECT ?execution ?interaction WHERE { GRAPH <${graphIri(id)}> { ?execution hi:hasInteractionEpisode ?interaction } }
    `);
    expect(episodes.map((row) => [row.execution.value, row.interaction.value])).toEqual([
      [`${base}execution:explain-recommendations`, `${base}interaction:explain-recommendations`],
    ]);
    const team = await readTeam(id);
    expect(teamRows(team)).toHaveLength(2);
    expect(new Set(teamRows(team).map((row) => row[0]))).toEqual(new Set(s4.agents.map((agent) => agent.name)));
  }, 60_000);

  it('S3: saves distinct jurors with shared capability and evaluation, English hypotheses, and two unlinked interactions', async () => {
    const id = `${RUN}-s3`;
    const data = { ...structuredClone(s3), id };
    expect(await requestPreview(data, { baseUrl: api })).toMatchObject({
      kind: 'ok', preview: { triple_count: 135 },
    });
    expect(await storedTriples(id)).toBe(0);
    await saveAndTrack(data, 135);
    expect(await storedTriples(id)).toBe(135);
    const base = `urn:hi-app:scenario:${id}:`;
    const shared = await select(`
      PREFIX hi: <https://w3id.org/hi-ontology#>
      SELECT ?agent ?capability WHERE { GRAPH <${graphIri(id)}> {
        ?agent hi:hasCapability ?capability .
        ?capability hi:hasCapabilityConcept <https://w3id.org/hi-thesaurus/SelfReportingCapability> .
      } }
    `);
    expect(new Set(shared.map((row) => row.capability.value))).toEqual(new Set([`${base}capability:self-reporting`]));
    expect(new Set(shared.map((row) => row.agent.value))).toEqual(new Set([`${base}agent:human-juror-1`, `${base}agent:human-juror-2`]));
    const executions = await select(`
      PREFIX hi: <https://w3id.org/hi-ontology#>
      SELECT ?execution ?task ?agent ?evaluation ?experiment WHERE { GRAPH <${graphIri(id)}> {
        ?execution a hi:TaskExecution ; hi:realizesTask ?task ; hi:performedBy ?agent ; hi:evaluatedBy ?evaluation .
        ?evaluation hi:hasExperiment ?experiment .
      } }
    `);
    expect(executions).toHaveLength(5);
    expect(new Set(executions.map((row) => row.evaluation.value))).toEqual(new Set([`${base}evaluation:ai-intervention-impact`]));
    expect(new Set(executions.map((row) => row.experiment.value))).toEqual(new Set([`${base}experiment:deliberation-support`]));
    const statements = executions.filter((row) => row.task.value === `${base}task:provide-statement`);
    expect(statements).toHaveLength(2);
    expect(new Set(statements.map((row) => row.agent.value))).toEqual(new Set([`${base}agent:human-juror-1`, `${base}agent:human-juror-2`]));
    const interactions = await select(`
      PREFIX hi: <https://w3id.org/hi-ontology#>
      SELECT ?interaction ?participant ?execution WHERE { GRAPH <${graphIri(id)}> {
        ?interaction a hi:Interaction ; hi:hasAgentInvolved ?participant .
        OPTIONAL { ?execution hi:hasInteractionEpisode ?interaction }
      } }
    `);
    expect(interactions).toHaveLength(6);
    expect(new Set(interactions.map((row) => row.interaction.value)).size).toBe(2);
    for (const interaction of s3.interactions) {
      expect(new Set(interactions.filter((row) => row.interaction.value === `${base}interaction:${interaction.id}`).map((row) => row.participant.value)))
        .toEqual(new Set(s3.agents.map((agent) => `${base}agent:${agent.id}`)));
    }
    expect(interactions.every((row) => !row.execution)).toBe(true);
    const hypotheses = await select(`
      PREFIX hi: <https://w3id.org/hi-ontology#>
      SELECT ?nullHypothesis ?alternativeHypothesis (LANG(?nullHypothesis) AS ?nullLanguage) (LANG(?alternativeHypothesis) AS ?alternativeLanguage)
      WHERE { GRAPH <${graphIri(id)}> {
        <${base}experiment:deliberation-support> hi:hasNullHypothesis ?nullHypothesis ; hi:hasAlternativeHypothesis ?alternativeHypothesis .
      } }
    `);
    expect(hypotheses).toHaveLength(1);
    expect(hypotheses[0].nullHypothesis.value).toBe(s3.experiments[0].null_hypothesis);
    expect(hypotheses[0].alternativeHypothesis.value).toBe(s3.experiments[0].alternative_hypothesis);
    expect(hypotheses[0].nullLanguage.value).toBe('en');
    expect(hypotheses[0].alternativeLanguage.value).toBe('en');
    const team = await readTeam(id);
    expect(new Set(teamRows(team).map((row) => row[0]))).toEqual(new Set(s3.agents.map((agent) => agent.name)));
    expect(teamRows(team)).toHaveLength(3);
  }, 60_000);

  it('S2: previews, saves, and queries the complete reconstruction without merging entities', async () => {
    const id = `${RUN}-s2`;
    const data = { ...structuredClone(s2), id };
    expect(await requestPreview(data, { baseUrl: api })).toMatchObject({
      kind: 'ok', preview: { triple_count: 195 },
    });
    expect(await storedTriples(id)).toBe(0);
    await saveAndTrack(data, 195);
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
    const team = await readTeam(id);
    expect(teamRows(team).map((row) => row[0])).toEqual(['Human technician', 'Robot manipulator']);
  }, 60_000);

  it('S1: preview, save, CQ1, and the Workbench link for the saved graph', async () => {
    const id = `${RUN}-s1`;
    const data = scenario(id);
    expect(await requestPreview(data, { baseUrl: api })).toMatchObject({
      kind: 'ok', preview: { triple_count: 127 },
    });
    expect(await storedTriples(id)).toBe(0);
    const saved = await saveAndTrack(data, 127);
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

    const team = await readTeam(id);
    expect(team.use_case_name).toBe('Personal assistant HI system');
    expect(teamRows(team)).toEqual([
      ['AI assistant', 'Artificial Agent', 'System Assistant Role'],
      ['Human user', 'Human Agent', 'User Role'],
    ]);

    const link = saved.workbench_graph_url;
    expect(link).toBe(`${GRAPHDB}/resource?uri=${encodeURIComponent(graphIri(id))}&role=context`);
    // Browsers request HTML and get the Workbench page (other Accept headers get RDF4J's 400).
    const page = await fetch(link, { headers: { Accept: 'text/html' } });
    expect(page.status).toBe(200);
    expect(page.headers.get('content-type')).toContain('text/html');
  }, 60_000);

  it('persists only selected goal requirements while retaining every task and execution', async () => {
    const id = `${RUN}-goal-subset`;
    const data = scenario(id, (draft) => { draft.goal.required_tasks = ['data-collection']; });
    await saveAndTrack(data, 125);
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
    const team = await readTeam(id);
    expect(teamRows(team)).toHaveLength(2);
  }, 60_000);

  it('stores one shared capability with explicit links to multiple agents and tasks', async () => {
    const id = `${RUN}-shared-capability`;
    const data = scenario(id, (data) => {
      delete data.executions; // Exercise the capability workflow without execution assignments.
      delete data.interactions;
      delete data.experiments;
      delete data.evaluations;
      data.agents.forEach((/** @type {import('../src/lib/scenario.js').Agent} */ agent) => { agent.name = 'Same display name'; });
      data.capabilities = [{
        id: 'shared', concept: 'ReasoningCapability',
        agents: ['human-user', 'ai-assistant'], tasks: ['data-collection', 'conflict-resolution'],
      }];
    });
    await saveAndTrack(data);
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
    const data = scenario(id, (data) => {
      delete data.interactions;
      delete data.experiments;
      delete data.evaluations;
      data.executions = [
        { id: 'first', concept: 'DataCollectionTaskExecution', task: 'data-collection', agent: 'human-user', method: 'DataCollectionMethod' },
        { id: 'second', concept: 'DataCollectionTaskExecution', task: 'data-collection', agent: 'ai-assistant' },
        { id: 'repeat', concept: 'DataCollectionTaskExecution', task: 'data-collection', agent: 'human-user' },
      ];
    });
    await saveAndTrack(data);
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
    const data = scenario(id, (data) => {
      const metrics = ['FairOutcomeMetric', 'UndueInfluenceMetric', 'ExplanationClarityMetric'];
      data.experiments = [{
        ...data.experiments[0], id: 'shared', concept: 'DeliberationSupportExperiment', metrics,
        hypothesis_language: 'en', description: 'Shared experiment description.',
      }];
      data.evaluations = [{
        id: 'shared', concept: 'AIInterventionImpactEvaluation', metrics, experiment: 'shared',
        executions: data.executions.map((/** @type {{ id: string }} */ e) => e.id), description: 'Shared evaluation description.',
      }];
    });
    await saveAndTrack(data);
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
    const data = scenario(id, (data) => {
      data.agents.push({ ...data.agents[0], id: 'second-human' });
      data.interactions = [
        { id: 'shared', intent: 'ExplanationIntent', modality: 'VerbalDialogueModality', agents: ['ai-assistant', 'human-user', 'second-human'], executions: ['explanation', 'conflict-resolution'], description: 'Shared English description.' },
        { id: 'unlinked', intent: 'DeliberationIntent', modality: 'TextChatModality', agents: ['ai-assistant', 'human-user'], executions: [] },
        { id: 'also-shared', intent: 'ExplanationIntent', modality: 'VerbalDialogueModality', agents: ['ai-assistant', 'human-user'], executions: ['explanation'] },
      ];
    });
    await saveAndTrack(data);
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
    const data = scenario(id, (data) => {
      data.agents.push({ id: 'second-human', name: 'Clinician', kind: 'human', roles: ['HumanUserRole', 'ClinicianRole'] });
    });
    await saveAndTrack(data, 133);
    const team = await readTeam(id);
    expect(teamRows(team)).toEqual([
      ['AI assistant', 'Artificial Agent', 'System Assistant Role'],
      ['Human user', 'Human Agent', 'User Role'],
      ['Clinician', 'Human Agent', 'Clinician Role, User Role'],
    ]);
  }, 60_000);

  it('saves revised data under a fresh scenario ID without touching the old graph', async () => {
    const id = `${RUN}-edit`;
    await saveAndTrack(scenario(id), 127);
    const newId = `${id}-revised`;
    const revised = scenario(newId, (data) => { data.agents[0].name = 'Renamed participant'; });
    await saveAndTrack(revised, 127);
    expect(await storedLabel(newId, 'human-user')).toEqual(['Renamed participant']);
    expect(await storedLabel(id, 'human-user')).toEqual(['Human user']);
    expect(await storedTriples(id)).toBe(127);
  }, 60_000);

  it('409: an existing ID is reported and never overwritten', async () => {
    const id = `${RUN}-conflict`;
    await saveAndTrack(scenario(id), 127);
    const conflicting = scenario(id, (data) => { data.agents[0].name = 'Different person'; });
    expect(await saveScenario(conflicting, { baseUrl: api })).toMatchObject({
      kind: 'rejected', status: 409, error: { code: 'scenario_exists' },
    });
    expect(await storedLabel(id, 'human-user')).toEqual(['Human user']);
    expect(await storedTriples(id)).toBe(127);
  }, 60_000);

  it('503: GraphDB unavailable is reported as not saved, while preview still works', async () => {
    const id = `${RUN}-down`;
    const data = scenario(id);
    const options = { baseUrl: apiWithoutGraphDB };
    expect(await requestPreview(data, options)).toMatchObject({
      kind: 'ok', preview: { triple_count: 127 },
    });
    expect(await saveScenario(data, options)).toMatchObject({
      kind: 'rejected', status: 503, error: { code: 'graphdb_unavailable' },
    });
    expect(await storedTriples(id)).toBe(0);
  }, 60_000);

  it('a failed CQ1 query does not undo a successful save', async () => {
    const id = `${RUN}-cq1-down`;
    await saveAndTrack(scenario(id), 127);
    expect(await fetchTeam(id, { baseUrl: apiWithoutGraphDB })).toMatchObject({
      kind: 'rejected', status: 503, error: { code: 'graphdb_unavailable' },
    });
    expect(await storedTriples(id)).toBe(127);
    expect((await readTeam(id)).members).toHaveLength(2);
  }, 60_000);
});
