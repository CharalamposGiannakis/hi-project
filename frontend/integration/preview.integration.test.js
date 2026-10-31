// @vitest-environment jsdom
// Svelte App → FastAPI → RDF → SHACL, against a real backend process. Run with
// `npm run test:integration`; set PYTHON to choose the interpreter (default: ../.venv, then `python`).
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';
import legacyExample from '../../examples/s1.json';
import s2 from '../../examples/s2.json';
import s3 from '../../examples/s3.json';
import { requestPreview } from '../src/lib/api.js';
import { concepts } from '../src/lib/scenario.js';
import { PYTHON, ROOT, closedPort, startBackend } from './backend.js';

const example = { ...legacyExample, goal: { ...legacyExample.goal, required_tasks: legacyExample.tasks.map((task) => task.id) } };
const reconstructions = [{ label: 'S2', canonical: s2, triples: 195 }, { label: 'S3', canonical: s3, triples: 135 }];

/** @type {{ url: string, stop: () => void } | undefined} */
let backend;
let baseUrl = '';

beforeAll(async () => {
  backend = await startBackend();
  baseUrl = backend.url;
}, 60_000);

afterAll(() => {
  backend?.stop();
});

/** @type {Record<string, any> | undefined} */
let app;
afterEach(() => {
  if (app) unmount(app);
  app = undefined;
  document.body.innerHTML = '';
  vi.unstubAllEnvs();
});

/** Mount the real App against `apiUrl`. */
async function mountApp(apiUrl = baseUrl) {
  vi.stubEnv('VITE_API_URL', apiUrl);
  const { default: App } = await import('../src/App.svelte');
  app = mount(App, { target: document.body });
}

const text = () => document.body.textContent ?? '';
/** @param {string} label */
function clickButton(label) {
  const button = [...document.querySelectorAll('button')].find((b) => b.textContent?.trim() === label);
  if (!button) throw new Error(`No button "${label}"`);
  button.click();
  flushSync();
}
/** @param {() => boolean} condition */
async function until(condition) {
  await vi.waitFor(() => {
    flushSync();
    if (!condition()) throw new Error('condition not met');
  }, { timeout: 15_000, interval: 50 });
}

/** @param {ParentNode} root @param {string} label @param {string} value */
function selectValue(root, label, value) {
  const control = [...root.querySelectorAll('label')].find((l) => l.textContent?.trim() === label)?.control;
  if (!(control instanceof HTMLSelectElement)) throw new Error(`No select "${label}"`);
  control.value = value;
  control.dispatchEvent(new Event('change', { bubbles: true }));
  flushSync();
}

/** @param {ParentNode} root @param {string} label @param {string} value */
function enterText(root, label, value) {
  const control = [...root.querySelectorAll('label')].find((l) => l.textContent?.trim() === label)?.control;
  if (!(control instanceof HTMLTextAreaElement || control instanceof HTMLInputElement)) throw new Error(`No text input "${label}"`);
  control.value = value;
  control.dispatchEvent(new Event('input', { bubbles: true }));
  flushSync();
}

describe('Svelte → FastAPI → RDF → SHACL', () => {
  it.each(reconstructions)('imports $label, exports it through Copy, reimports it, and previews identical RDF', async ({ canonical, triples }) => {
    await mountApp();
    /** @param {string} json */
    async function importJson(json) {
      const input = /** @type {HTMLInputElement} */ (document.querySelector('input[type=file]'));
      Object.defineProperty(input, 'files', { value: [{ name: 'example.json', text: async () => json }], configurable: true });
      input.dispatchEvent(new Event('change', { bubbles: true }));
      await until(() => text().includes('Loaded example.json'));
    }
    await importJson(JSON.stringify(canonical));
    expect(JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}')).toEqual(canonical);
    const expected = await requestPreview(canonical, { baseUrl });
    expect(expected.kind).toBe('ok');
    if (expected.kind !== 'ok') throw new Error(JSON.stringify(expected));
    clickButton('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    expect(text()).toContain(`${triples} triples · not saved`);
    expect(document.querySelector('pre.rdf')?.textContent).toBe(expected.preview.rdf);

    let exported = '';
    const clipboard = Object.getOwnPropertyDescriptor(navigator, 'clipboard');
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async (/** @type {string} */ value) => { exported = value; } } });
    try {
      clickButton('Copy');
      await until(() => text().includes('JSON copied to the clipboard.'));
    } finally {
      if (clipboard) Object.defineProperty(navigator, 'clipboard', clipboard);
      else Reflect.deleteProperty(navigator, 'clipboard');
    }
    expect(JSON.parse(exported)).toEqual(canonical);
    unmount(/** @type {Record<string, any>} */ (app));
    app = undefined;
    await mountApp();
    await importJson(exported);
    expect(JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}')).toEqual(canonical);
    clickButton('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    expect(document.querySelector('pre.rdf')?.textContent).toBe(expected.preview.rdf);
  });

  it.each(reconstructions)('enters the complete $label through the form with independent entities and source relationships', async ({ canonical, triples }) => {
    await mountApp(); // Start with a blank form; do not load or inject scenario JSON.
    const draft = () => JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}');
    /** @type {Record<string, Record<string, string>>} */
    const ids = { tasks: {}, agents: {}, capabilities: {}, executions: {}, experiments: {}, evaluations: {}, interactions: {} };
    /** @param {ParentNode} root @param {string} label @param {string[]} values */
    function selectChecks(root, label, values) {
      const fieldset = [...root.querySelectorAll('fieldset')].find((f) => f.querySelector('legend')?.textContent?.trim() === label);
      if (!fieldset) throw new Error(`No checklist ${label}`);
      const controls = [...fieldset.querySelectorAll('input[type=checkbox]')].map((input) => /** @type {HTMLInputElement} */ (input));
      for (const input of controls) {
        if (input.checked && !values.includes(input.value)) { input.click(); flushSync(); }
      }
      for (const value of values) {
        const input = controls.find((control) => control.value === value);
        if (!input) throw new Error(`No ${label} option ${value}`);
        if (!input.checked) { input.click(); flushSync(); }
      }
    }
    /** @param {string} kind @param {string} collection @param {string} sourceId */
    function addRecord(kind, collection, sourceId) {
      clickButton(`Add ${kind}`);
      const section = /** @type {Element} */ ([...document.querySelectorAll(`[data-${kind}-id]`)].at(-1));
      ids[collection][sourceId] = draft()[collection].at(-1).id;
      return section;
    }
    const useCase = /** @type {Element} */ (document.querySelector('form > fieldset'));
    enterText(useCase, 'Name', canonical.use_case.name);
    selectValue(useCase, 'Use case type', canonical.use_case.concept);
    selectValue(useCase, 'Domain (optional)', canonical.use_case.domain);
    const goal = /** @type {Element} */ (document.querySelector('#goal-name')?.closest('fieldset'));
    enterText(goal, 'Name', canonical.goal.name);
    selectValue(goal, 'Goal type', canonical.goal.concept);
    clickButton('Add context');
    selectValue(document, 'Context type', canonical.context.concept);
    selectChecks(document, 'Phenomena', canonical.context.phenomena);
    selectChecks(document, 'Constraints', canonical.context.constraints);
    canonical.tasks.forEach((task, i) => {
      if (i > 0) clickButton('Add task');
      const id = draft().tasks[i].id;
      ids.tasks[task.id] = id;
      const section = /** @type {Element} */ (document.querySelector(`#task-${id}`)?.closest('section'));
      enterText(section, 'Name', task.name);
      selectValue(section, 'Task type', task.concept);
    });
    selectChecks(goal, 'Tasks required by this goal', canonical.goal.required_tasks.map((id) => ids.tasks[id]));
    for (const agent of canonical.agents) {
      let record = draft().agents.find((/** @type {any} */ a) => a.kind === agent.kind && !Object.values(ids.agents).includes(a.id));
      if (!record) {
        clickButton(`Add ${agent.kind} agent`);
        record = draft().agents.at(-1);
      }
      const id = record.id;
      ids.agents[agent.id] = id;
      const section = /** @type {Element} */ (document.querySelector(`#agent-${id}`)?.closest('section'));
      enterText(section, 'Name', agent.name);
      for (const role of agent.roles) {
        const label = concepts.Role.find((concept) => concept.id === role)?.label;
        const control = [...section.querySelectorAll('fieldset.roles label')].find((element) => element.textContent?.trim() === label)?.querySelector('input');
        if (!control) throw new Error(`No role ${role}`);
        control.click();
        flushSync();
      }
    }
    for (const capability of canonical.capabilities) {
      const section = addRecord('capability', 'capabilities', capability.id);
      selectValue(section, 'Capability type', capability.concept);
      selectChecks(section, 'Possessed by agents', capability.agents.map((id) => ids.agents[id]));
      selectChecks(section, 'Enables tasks', capability.tasks.map((id) => ids.tasks[id]));
    }
    for (const execution of canonical.executions) {
      const section = addRecord('execution', 'executions', execution.id);
      selectValue(section, 'Execution type', execution.concept);
      selectValue(section, 'Task', ids.tasks[execution.task]);
      selectValue(section, 'Agent', ids.agents[execution.agent]);
      if (execution.method) selectValue(section, 'Method (optional)', execution.method);
    }
    for (const experiment of canonical.experiments) {
      const section = addRecord('experiment', 'experiments', experiment.id);
      selectValue(section, 'Experiment type', experiment.concept);
      selectChecks(section, 'Metrics', experiment.metrics);
      enterText(section, 'Null hypothesis', experiment.null_hypothesis);
      enterText(section, 'Alternative hypothesis', experiment.alternative_hypothesis);
      if ('hypothesis_language' in experiment) selectValue(section, 'Hypothesis literal format', String(experiment.hypothesis_language));
    }
    for (const evaluation of canonical.evaluations) {
      const section = addRecord('evaluation', 'evaluations', evaluation.id);
      selectValue(section, 'Evaluation type', evaluation.concept);
      selectChecks(section, 'Metrics', evaluation.metrics);
      selectValue(section, 'Experiment', ids.experiments[evaluation.experiment]);
      selectChecks(section, 'Evaluated executions', evaluation.executions.map((id) => ids.executions[id]));
    }
    for (const interaction of canonical.interactions) {
      const section = addRecord('interaction', 'interactions', interaction.id);
      selectValue(section, 'Interaction intent', interaction.intent);
      selectValue(section, 'Interaction modality', interaction.modality);
      selectChecks(section, 'Participating agents', interaction.agents.map((id) => ids.agents[id]));
      selectChecks(section, 'Related executions (optional)', []);
    }
    const entered = draft();
    // Every field and relationship must match the canonical example modulo app-assigned IDs.
    const expected = {
      ...canonical, id: entered.id,
      use_case: { ...canonical.use_case, id: entered.use_case.id },
      goal: { ...canonical.goal, id: entered.goal.id, required_tasks: canonical.goal.required_tasks.map((id) => ids.tasks[id]) },
      tasks: canonical.tasks.map((task) => ({ ...task, id: ids.tasks[task.id] })),
      agents: canonical.agents.map((agent) => ({ ...agent, id: ids.agents[agent.id] })),
      capabilities: canonical.capabilities.map((capability) => ({ ...capability, id: ids.capabilities[capability.id], agents: capability.agents.map((id) => ids.agents[id]), tasks: capability.tasks.map((id) => ids.tasks[id]) })),
      executions: canonical.executions.map((execution) => ({ ...execution, id: ids.executions[execution.id], task: ids.tasks[execution.task], agent: ids.agents[execution.agent] })),
      experiments: canonical.experiments.map((experiment) => ({ ...experiment, id: ids.experiments[experiment.id] })),
      evaluations: canonical.evaluations.map((evaluation) => ({ ...evaluation, id: ids.evaluations[evaluation.id], experiment: ids.experiments[evaluation.experiment], executions: evaluation.executions.map((id) => ids.executions[id]) })),
      interactions: canonical.interactions.map((interaction) => ({ ...interaction, id: ids.interactions[interaction.id], agents: interaction.agents.map((id) => ids.agents[id]) })),
    };
    expect(new Set(Object.values(ids.agents)).size).toBe(canonical.agents.length);
    expect(entered.agents).toHaveLength(canonical.agents.length);
    // Extra human rows are appended after the initial human/artificial pair; row order is not identity.
    expected.agents.sort((a, b) => entered.agents.findIndex((/** @type {any} */ agent) => agent.id === a.id) - entered.agents.findIndex((/** @type {any} */ agent) => agent.id === b.id));
    expect(entered).toEqual(expected);
    clickButton('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    expect(text()).toContain(`${triples} triples · not saved`);
    const rdf = document.querySelector('pre.rdf')?.textContent ?? '';
    expect(rdf.match(/<https:\/\/w3id.org\/hi-ontology#requiresTask>/g)).toHaveLength(canonical.goal.required_tasks.length);
    expect(rdf).not.toContain('<https://w3id.org/hi-ontology#hasInteractionEpisode>');
    const preview = await requestPreview(expected, { baseUrl });
    expect(preview.kind).toBe('ok');
    if (preview.kind !== 'ok') throw new Error(JSON.stringify(preview));
    expect(rdf).toBe(preview.preview.rdf);
  }, 60_000);

  it('selects goal requirements explicitly and previews added tasks without requiring them', async () => {
    await mountApp();
    clickButton('Load S1 example'); // Legacy JSON initializes all three requirements.
    const goal = /** @type {Element} */ (document.querySelector('#goal-name')?.closest('fieldset'));
    const checklist = /** @type {Element} */ (goal.querySelector('fieldset'));
    expect(checklist.querySelector('legend')?.textContent).toBe('Tasks required by this goal');
    expect(checklist.querySelectorAll('input:checked')).toHaveLength(3);
    for (const id of ['conflict-resolution', 'explanation']) {
      /** @type {HTMLInputElement} */ (checklist.querySelector(`input[value="${id}"]`)).click();
      flushSync();
    }
    expect(JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}').goal.required_tasks).toEqual(['data-collection']);
    clickButton('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    expect(text()).toContain('125 triples · not saved');
    let rdf = document.querySelector('pre.rdf')?.textContent ?? '';
    expect(rdf.match(/<https:\/\/w3id.org\/hi-ontology#requiresTask>/g)).toHaveLength(1);
    for (const task of example.tasks) {
      expect(rdf).toContain(`<urn:hi-app:scenario:s1:task:${task.id}> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <https://w3id.org/hi-ontology#Task> .`);
    }
    expect(rdf).toContain('<urn:hi-app:scenario:s1:execution:explanation> <https://w3id.org/hi-ontology#realizesTask> <urn:hi-app:scenario:s1:task:explanation> .');

    clickButton('Add task');
    const draft = JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}');
    const id = draft.tasks.at(-1).id;
    const taskSection = /** @type {Element} */ (document.querySelector(`#task-${id}`)?.closest('section'));
    enterText(taskSection, 'Name', 'Supporting task');
    selectValue(taskSection, 'Task type', 'DataCollectionTask');
    expect(draft.goal.required_tasks).toEqual(['data-collection']);
    expect(/** @type {HTMLInputElement} */ (checklist.querySelector(`input[value="${id}"]`)).checked).toBe(false);
    clickButton('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    expect(text()).toContain('128 triples · not saved');
    rdf = document.querySelector('pre.rdf')?.textContent ?? '';
    expect(rdf).toContain(`<urn:hi-app:scenario:s1:task:${id}> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <https://w3id.org/hi-ontology#Task> .`);
    expect(rdf).not.toContain(`<urn:hi-app:scenario:s1:goal:user-wellbeing> <https://w3id.org/hi-ontology#requiresTask> <urn:hi-app:scenario:s1:task:${id}> .`);
  });

  it('removes task references and blocks preview and save until an empty requirement selection is repaired', async () => {
    await mountApp();
    const data = { ...structuredClone(example), capabilities: [], executions: [], evaluations: [], experiments: [], interactions: [] };
    data.goal.required_tasks = ['data-collection'];
    const input = /** @type {HTMLInputElement} */ (document.querySelector('input[type=file]'));
    Object.defineProperty(input, 'files', { value: [{ name: 'requirements.json', text: async () => JSON.stringify(data) }] });
    input.dispatchEvent(new Event('change', { bubbles: true }));
    await until(() => text().includes('Loaded requirements.json'));
    for (const id of ['conflict-resolution', 'data-collection']) {
      const section = /** @type {Element} */ (document.querySelector(`#task-${id}`)?.closest('section'));
      /** @type {HTMLButtonElement} */ (section.querySelector('button')).click();
      flushSync();
      expect(JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}').goal.required_tasks).toEqual(id === 'conflict-resolution' ? ['data-collection'] : []);
    }
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    try {
      clickButton('Validate & preview RDF');
      clickButton('Save to GraphDB');
      expect(text()).toContain('Choose at least one required task.');
      expect(fetchSpy).not.toHaveBeenCalled();
    } finally { fetchSpy.mockRestore(); }
    const goal = /** @type {Element} */ (document.querySelector('#goal-name')?.closest('fieldset'));
    /** @type {HTMLInputElement} */ (goal.querySelector('input[value="explanation"]')).click();
    flushSync();
    expect(JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}').goal.required_tasks).toEqual(['explanation']);
    clickButton('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    expect(document.querySelector('pre.rdf')?.textContent).toContain('<urn:hi-app:scenario:s1:goal:user-wellbeing> <https://w3id.org/hi-ontology#requiresTask> <urn:hi-app:scenario:s1:task:explanation> .');
  });

  it('enters all four S1 goal and task descriptions and previews English comments independently of names', async () => {
    await mountApp();
    clickButton('Load S1 example');
    const goal = /** @type {Element} */ (document.querySelector('#goal-name')?.closest('fieldset'));
    const tasks = example.tasks.map((task) => /** @type {Element} */ (document.querySelector(`#task-${task.id}`)?.closest('section')));
    for (const section of [goal, ...tasks]) {
      expect([...section.querySelectorAll('label')].some((label) => label.textContent === 'Name')).toBe(true);
      enterText(section, 'Description in English (optional)', '');
    }
    clickButton('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    expect(text()).toContain('123 triples · not saved'); // Legacy S1 without these comments.

    enterText(goal, 'Description in English (optional)', example.goal.description);
    expect(document.querySelector('pre.rdf')).toBeNull();
    example.tasks.forEach((task, i) => enterText(tasks[i], 'Description in English (optional)', task.description));
    expect(JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}')).toEqual(example);
    clickButton('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    expect(text()).toContain('127 triples · not saved');
    const rdf = document.querySelector('pre.rdf')?.textContent ?? '';
    for (const { kind, entity } of [{ kind: 'goal', entity: example.goal }, ...example.tasks.map((task) => ({ kind: 'task', entity: task }))]) {
      expect(rdf).toContain(`<urn:hi-app:scenario:s1:${kind}:${entity.id}> <http://www.w3.org/2000/01/rdf-schema#comment> "${entity.description}"@en .`);
      expect(rdf).toContain(`<urn:hi-app:scenario:s1:${kind}:${entity.id}> <http://www.w3.org/2000/01/rdf-schema#label> "${entity.name}" .`);
    }
  });

  it('enters S1 interaction explicitly and supports unlinked descriptions', async () => {
    await mountApp();
    clickButton('Load S1 example');
    clickButton('Remove interaction');
    expect(JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}')).not.toHaveProperty('interactions');
    clickButton('Add interaction');
    const section = /** @type {Element} */ (document.querySelector('[data-interaction-id]'));
    selectValue(section, 'Interaction intent', example.interactions[0].intent);
    selectValue(section, 'Interaction modality', example.interactions[0].modality);
    /** @type {HTMLInputElement} */ (section.querySelector('input[value="explanation"]')).click();
    flushSync();
    expect(JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}').interactions[0].agents).toEqual([]);
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    try {
      clickButton('Validate & preview RDF');
      expect(fetchSpy).not.toHaveBeenCalled();
      expect(text()).toContain('Choose at least two distinct agents.');
    } finally { fetchSpy.mockRestore(); }
    for (const id of example.interactions[0].agents) {
      /** @type {HTMLInputElement} */ (section.querySelector(`input[value="${id}"]`)).click();
      flushSync();
    }
    const entered = JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}').interactions[0];
    expect(entered).toMatchObject({ intent: 'ExplanationIntent', modality: 'VerbalDialogueModality', agents: example.interactions[0].agents, executions: ['explanation'] });
    clickButton('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    expect(text()).toContain('127 triples · not saved');
    /** @type {HTMLInputElement} */ (section.querySelector('input[value="explanation"]')).click();
    flushSync();
    expect(document.querySelector('pre.rdf')).toBeNull();
    clickButton('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    expect(text()).toContain('126 triples · not saved');
    enterText(section, 'Description in English (optional)', 'User-entered interaction description.');
    const changed = JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}').interactions[0];
    expect(changed.id).toBe(entered.id);
    expect(changed.executions).toEqual([]);
    clickButton('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    expect(document.querySelector('pre.rdf')?.textContent).toContain('"User-entered interaction description."@en');
  });

  it.each(['agent', 'execution'])('preserves interaction data after deleting a referenced %s and allows repair', async (kind) => {
    await mountApp();
    const data = {
      ...structuredClone(example), evaluations: [], experiments: [],
      executions: example.executions.filter((e) => e.agent === 'ai-assistant'),
      agents: [...example.agents, { ...example.agents[0], id: 'replacement-human', name: 'Replacement human' }],
      interactions: example.interactions.map((i) => ({ ...i, description: 'Preserve this description.' })),
    };
    const input = /** @type {HTMLInputElement} */ (document.querySelector('input[type=file]'));
    Object.defineProperty(input, 'files', { value: [{ name: 'interactions.json', text: async () => JSON.stringify(data) }] });
    input.dispatchEvent(new Event('change', { bubbles: true }));
    await until(() => text().includes('Loaded interactions.json'));
    const id = kind === 'agent' ? 'human-user' : 'explanation';
    const section = kind === 'agent' ? document.querySelector('#agent-human-user')?.closest('section') : document.querySelector('[data-execution-id="explanation"]');
    section?.querySelector('button')?.click();
    flushSync();
    expect(text()).toContain(`Referenced records no longer exist: ${id}`);
    expect(JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}').interactions).toEqual(data.interactions);
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    try {
      clickButton('Validate & preview RDF');
      clickButton('Save to GraphDB');
      expect(fetchSpy).not.toHaveBeenCalled();
    } finally { fetchSpy.mockRestore(); }
    const interaction = /** @type {Element} */ (document.querySelector('[data-interaction-id]'));
    const replacement = kind === 'agent' ? 'replacement-human' : 'conflict-resolution';
    /** @type {HTMLInputElement} */ (interaction.querySelector(`input[value="${replacement}"]`)).click();
    flushSync();
    /** @type {HTMLInputElement} */ (interaction.querySelector(`input[value="${id}"]`)).click();
    flushSync();
    const repaired = JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}').interactions[0];
    expect(repaired.id).toBe(data.interactions[0].id);
    expect(repaired.description).toBe(data.interactions[0].description);
    clickButton('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
  });

  it('enters all S1 experiments and evaluations through the form', async () => {
    await mountApp();
    clickButton('Load S1 example');
    for (const _ of example.evaluations) clickButton('Remove evaluation');
    for (const _ of example.experiments) clickButton('Remove experiment');
    for (const experiment of example.experiments) {
      clickButton('Add experiment');
      const section = /** @type {Element} */ ([...document.querySelectorAll('[data-experiment-id]')].at(-1));
      selectValue(section, 'Experiment type', experiment.concept);
      for (const id of experiment.metrics) {
        /** @type {HTMLInputElement} */ (section.querySelector(`input[value="${id}"]`)).click();
        flushSync();
      }
      enterText(section, 'Null hypothesis', experiment.null_hypothesis);
      enterText(section, 'Alternative hypothesis', experiment.alternative_hypothesis);
    }
    const created = /** @type {import('../src/lib/scenario.js').Scenario} */ (JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}'));
    for (const evaluation of example.evaluations) {
      clickButton('Add evaluation');
      const section = /** @type {Element} */ ([...document.querySelectorAll('[data-evaluation-id]')].at(-1));
      selectValue(section, 'Evaluation type', evaluation.concept);
      const index = example.experiments.findIndex((e) => e.id === evaluation.experiment);
      selectValue(section, 'Experiment', created.experiments[index].id);
      for (const id of [...evaluation.metrics, ...evaluation.executions]) {
        /** @type {HTMLInputElement} */ (section.querySelector(`input[value="${id}"]`)).click();
        flushSync();
      }
      enterText(section, 'Description in English (optional)', evaluation.description);
    }
    const entered = /** @type {import('../src/lib/scenario.js').Scenario} */ (JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}'));
    expect(entered.experiments.map(({ id, ...facts }) => facts)).toEqual(example.experiments.map(({ id, ...facts }) => facts));
    expect(entered.evaluations.map(({ id, experiment, ...facts }) => facts)).toEqual(example.evaluations.map(({ id, experiment, ...facts }) => facts));
    clickButton('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    expect(text()).toContain('127 triples · not saved');
    const firstExperiment = /** @type {Element} */ (document.querySelector('[data-experiment-id]'));
    selectValue(firstExperiment, 'Hypothesis literal format', 'en');
    expect(document.querySelector('pre.rdf')).toBeNull();
    clickButton('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    expect(document.querySelector('pre.rdf')?.textContent).toContain(`"${example.experiments[0].null_hypothesis}"@en`);
    const firstEvaluation = /** @type {Element} */ (document.querySelector('[data-evaluation-id]'));
    for (const section of [firstExperiment, firstEvaluation]) {
      /** @type {HTMLInputElement} */ (section.querySelector('input[value="FairOutcomeMetric"]')).click();
      flushSync();
    }
    /** @type {HTMLInputElement} */ (firstEvaluation.querySelector('input[value="conflict-resolution"]')).click();
    flushSync();
    clickButton('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    expect(text()).toContain('130 triples · not saved');
  });

  it.each(['experiment', 'execution'])('keeps evaluation data when a referenced %s is deleted and supports repair', async (kind) => {
    await mountApp();
    clickButton('Load S1 example');
    const id = kind === 'experiment' ? 'data-collection-quality' : 'data-collection';
    document.querySelector(`[data-${kind}-id="${id}"] button`)?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    flushSync();
    expect(JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}').evaluations).toEqual(example.evaluations);
    expect(text()).toContain(kind === 'experiment' ? `"${id}" no longer exists` : `Referenced records no longer exist: ${id}`);
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    try {
      clickButton('Validate & preview RDF');
      clickButton('Save to GraphDB');
      expect(fetchSpy).not.toHaveBeenCalled();
    } finally { fetchSpy.mockRestore(); }
    const evaluation = /** @type {Element} */ (document.querySelector('[data-evaluation-id="data-collection-quality"]'));
    if (kind === 'experiment') selectValue(evaluation, 'Experiment', 'conflict-accuracy');
    else {
      /** @type {HTMLInputElement} */ (evaluation.querySelector('input[value="conflict-resolution"]')).click();
      flushSync();
      /** @type {HTMLInputElement} */ (evaluation.querySelector('input[value="data-collection"]')).click();
      flushSync();
    }
    const repaired = JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}').evaluations[0];
    expect(repaired.id).toBe(example.evaluations[0].id);
    expect(repaired.description).toBe(example.evaluations[0].description);
    clickButton('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
  });

  it('enters all S1 executions through the form and supports optional methods', async () => {
    await mountApp();
    clickButton('Load S1 example');
    clickButton('Remove interaction');
    for (const _ of example.evaluations) clickButton('Remove evaluation');
    for (const _ of example.experiments) clickButton('Remove experiment');
    for (const _ of example.executions) clickButton('Remove execution');
    expect(JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}')).not.toHaveProperty('executions');
    for (const execution of example.executions) {
      clickButton('Add execution');
      const section = document.querySelectorAll('[data-execution-id]').item(document.querySelectorAll('[data-execution-id]').length - 1);
      selectValue(section, 'Execution type', execution.concept);
      selectValue(section, 'Task', execution.task);
      selectValue(section, 'Agent', execution.agent);
      selectValue(section, 'Method (optional)', execution.method);
    }
    const entered = /** @type {import('../src/lib/scenario.js').Scenario} */ (JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}'));
    expect(entered.executions.map(({ id, ...facts }) => facts)).toEqual(example.executions.map(({ id, ...facts }) => facts));
    expect(new Set(entered.executions.map((e) => e.id)).size).toBe(3);
    clickButton('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    expect(text()).toContain('88 triples · not saved');
    selectValue(/** @type {Element} */ (document.querySelector('[data-execution-id]')), 'Method (optional)', '');
    expect(document.querySelector('pre.rdf')).toBeNull();
    expect(JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}').executions[0]).not.toHaveProperty('method');
    clickButton('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    expect(text()).toContain('87 triples · not saved');
  });

  it.each(['agent', 'task'])('preserves executions after deleting a referenced %s and requires repair', async (kind) => {
    await mountApp();
    const { interactions: _interactions, ...data } = structuredClone(example);
    data.agents.push({ ...data.agents[0], id: 'replacement-human', name: 'Replacement human' });
    const input = /** @type {HTMLInputElement} */ (document.querySelector('input[type=file]'));
    Object.defineProperty(input, 'files', { value: [{ name: 'executions.json', text: async () => JSON.stringify(data) }] });
    input.dispatchEvent(new Event('change', { bubbles: true }));
    await until(() => text().includes('Loaded executions.json'));
    const id = kind === 'agent' ? 'human-user' : 'data-collection';
    const entity = document.querySelector(`#${kind}-${id}`)?.closest('section');
    entity?.querySelector('button')?.click();
    flushSync();
    expect(text()).toContain(`"${id}" no longer exists`);
    expect(JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}').executions).toEqual(data.executions);
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    try {
      clickButton('Validate & preview RDF');
      clickButton('Save to GraphDB');
      expect(fetchSpy).not.toHaveBeenCalled();
    } finally {
      fetchSpy.mockRestore();
    }
    const execution = /** @type {Element} */ (document.querySelector('[data-execution-id="data-collection"]'));
    selectValue(execution, kind === 'agent' ? 'Agent' : 'Task', kind === 'agent' ? 'replacement-human' : 'explanation');
    expect(text()).not.toContain(`"${id}" no longer exists`);
    const repaired = JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}').executions[0];
    expect(repaired.id).toBe(data.executions[0].id);
    expect(repaired.method).toBe(data.executions[0].method);
    clickButton('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
  });

  it('enters all four S1 capabilities through the form and shares their references', async () => {
    await mountApp();
    clickButton('Load S1 example');
    for (const _ of example.capabilities) clickButton('Remove capability');
    expect(JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}')).not.toHaveProperty('capabilities');
    for (const capability of example.capabilities) {
      clickButton('Add capability');
      const section = [...document.querySelectorAll('[data-capability-id]')].at(-1);
      const select = /** @type {HTMLSelectElement} */ (section?.querySelector('select'));
      select.value = capability.concept;
      select.dispatchEvent(new Event('change', { bubbles: true }));
      flushSync();
      for (const id of [...capability.agents, ...capability.tasks]) {
        /** @type {HTMLInputElement} */ (section?.querySelector(`input[value="${id}"]`)).click();
        flushSync();
      }
    }
    const entered = /** @type {import('../src/lib/scenario.js').Scenario} */ (JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}'));
    expect(entered.capabilities.map(({ id, ...facts }) => facts)).toEqual(example.capabilities.map(({ id, ...facts }) => facts));
    expect(new Set(entered.capabilities.map((c) => c.id)).size).toBe(4);
    clickButton('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    expect(text()).toContain('127 triples · not saved');

    const first = document.querySelector('[data-capability-id]');
    for (const id of ['human-user', 'conflict-resolution']) {
      /** @type {HTMLInputElement} */ (first?.querySelector(`input[value="${id}"]`)).click();
      flushSync();
    }
    const changed = JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}').capabilities[0];
    expect(changed.id).toBe(entered.capabilities[0].id);
    expect(changed.agents).toEqual(['ai-assistant', 'human-user']);
    expect(changed.tasks).toEqual(['data-collection', 'conflict-resolution']);
    expect(document.querySelector('pre.rdf')).toBeNull();
    clickButton('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    expect(text()).toContain('130 triples · not saved');
  });

  it('enters the complete original S1 Context through the form', async () => {
    await mountApp();
    clickButton('Load S1 example');
    clickButton('Remove context');
    expect(JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}')).not.toHaveProperty('context');
    clickButton('Add context');
    clickButton('Validate & preview RDF');
    expect(text()).toContain('Choose a concept.');

    const label = [...document.querySelectorAll('label')].find((l) => l.textContent?.trim() === 'Context type');
    const select = /** @type {HTMLSelectElement} */ (label?.control);
    select.value = example.context.concept;
    select.dispatchEvent(new Event('change', { bubbles: true }));
    flushSync();
    for (const id of [...example.context.phenomena, ...example.context.constraints]) {
      const concept = [...concepts.Phenomenon, ...concepts.Constraint].find((c) => c.id === id);
      const checkboxLabel = [...document.querySelectorAll('fieldset.concepts label')].find((l) => l.textContent?.trim() === concept?.label);
      expect(checkboxLabel, `HINT option ${id}`).toBeDefined();
      /** @type {HTMLInputElement} */ (checkboxLabel?.querySelector('input')).click();
      flushSync();
    }
    const description = /** @type {HTMLTextAreaElement} */ (document.querySelector('#context-description'));
    description.value = example.context.description;
    description.dispatchEvent(new Event('input', { bubbles: true }));
    flushSync();
    expect(JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}').context).toEqual(example.context);

    clickButton('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    expect(text()).toContain('127 triples · not saved');
    const rdf = document.querySelector('pre.rdf')?.textContent ?? '';
    expect(rdf).toContain('<urn:hi-app:scenario:s1:context>');
    expect(rdf).toContain(`"${example.context.description}"@en`);
    description.value = 'Edited context';
    description.dispatchEvent(new Event('input', { bubbles: true }));
    flushSync();
    expect(document.querySelector('pre.rdf')).toBeNull();
  });

  it('imports Context JSON through the file input', async () => {
    await mountApp();
    const input = /** @type {HTMLInputElement} */ (document.querySelector('input[type=file]'));
    Object.defineProperty(input, 'files', { value: [{ name: 'context.json', text: async () => JSON.stringify(example) }] });
    input.dispatchEvent(new Event('change', { bubbles: true }));
    await until(() => text().includes('Loaded context.json'));
    expect(JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}')).toEqual(example);
    expect(/** @type {HTMLTextAreaElement} */ (document.querySelector('#context-description')).value).toBe(example.context.description);
    expect(/** @type {HTMLTextAreaElement} */ (document.querySelector('#goal-description')).value).toBe(example.goal.description);
    for (const task of example.tasks) {
      expect(/** @type {HTMLTextAreaElement} */ (document.querySelector(`#task-description-${task.id}`)).value).toBe(task.description);
    }
  });

  it('previews S1 with exactly the RDF the Python pipeline generates, and invalidates it on edit', async () => {
    // The CLI's --output file always uses LF line endings (stdout may not on Windows).
    const dir = mkdtempSync(join(tmpdir(), 'hi-preview-'));
    const output = join(dir, 's1.nt');
    const cli = spawnSync(PYTHON, ['-m', 'hi_scenario', join(ROOT, 'examples/s1.json'), '--output', output], { cwd: ROOT, encoding: 'utf-8' });
    expect(cli.status, cli.stderr).toBe(0);
    const expected = readFileSync(output, 'utf-8');
    rmSync(dir, { recursive: true });

    await mountApp();
    clickButton('Load S1 example');
    clickButton('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    expect(text()).toContain('127 triples · not saved');
    expect(document.querySelector('pre.rdf')?.textContent).toBe(expected);

    const name = /** @type {HTMLInputElement} */ (document.querySelector('#agent-human-user'));
    name.value = 'Renamed participant';
    name.dispatchEvent(new Event('input', { bubbles: true }));
    flushSync();
    expect(text()).toContain('changed since the last preview');
    expect(document.querySelector('pre.rdf')).toBeNull();

    clickButton('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    expect(document.querySelector('pre.rdf')?.textContent).toContain(
      '<urn:hi-app:scenario:s1:agent:human-user> <http://www.w3.org/2000/01/rdf-schema#label> "Renamed participant" .',
    );
  }, 30_000);

  it('blocks incomplete forms locally without calling the backend', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    await mountApp();
    clickButton('Validate & preview RDF');
    expect(text()).toContain('Complete the highlighted fields first');
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it('shows an unavailable backend in the UI', async () => {
    await mountApp(`http://127.0.0.1:${await closedPort()}`);
    clickButton('Load S1 example');
    clickButton('Validate & preview RDF');
    await until(() => text().includes('Preview unavailable'));
    expect(text()).toContain('could not be reached');
    expect(document.querySelector('pre.rdf')).toBeNull();
  });

  it('returns the backend authoritative rejections that local checks cannot see', async () => {
    const vocabulary = structuredClone(example);
    vocabulary.agents[0].roles = ['MadeUpRole'];
    expect(await requestPreview(vocabulary, { baseUrl })).toEqual({
      kind: 'rejected',
      status: 422,
      error: expect.objectContaining({ code: 'invalid_vocabulary', message: 'Unknown HINT concept: MadeUpRole' }),
    });

    /** @type {any} */
    const structure = structuredClone(example);
    delete structure.goal;
    const result = await requestPreview(structure, { baseUrl });
    expect(result.kind).toBe('rejected');
    if (result.kind === 'rejected') {
      expect(result.error.code).toBe('invalid_request');
      expect(result.error.issues).toContainEqual(expect.objectContaining({ location: ['body', 'goal'] }));
    }
  });

  it('allows the Vite development origin through CORS, and only that origin', async () => {
    /** @param {string} origin */
    const preflight = (origin) =>
      fetch(`${baseUrl}/scenarios/preview`, {
        method: 'OPTIONS',
        headers: { Origin: origin, 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'content-type' },
      });
    const allowed = await preflight('http://localhost:5173');
    expect(allowed.status).toBe(200);
    expect(allowed.headers.get('access-control-allow-origin')).toBe('http://localhost:5173');
    const other = await preflight('http://localhost:5174');
    expect(other.headers.get('access-control-allow-origin')).toBeNull();
  });
});
