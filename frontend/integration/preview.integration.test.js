// @vitest-environment jsdom
// Svelte App → FastAPI → mocked Nebula transport and real RDF/SHACL. Run with
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
import s4 from '../../examples/s4.json';
import s5 from '../../examples/s5.json';
import s6 from '../../examples/s6.json';
import s7 from '../../examples/s7.json';
import { requestPreview } from '../src/lib/api.js';
import { requestScenarioJson } from '../src/lib/json-viewer-channel.js';
import { PYTHON, ROOT, closedPort, startBackend } from './backend.js';

const example = { ...legacyExample, goal: { ...legacyExample.goal, required_tasks: legacyExample.tasks.map((task) => task.id) } };
const reconstructions = [
  { label: 'S2', canonical: s2, triples: 195 },
  { label: 'S3', canonical: s3, triples: 135 },
  { label: 'S4', canonical: s4, triples: 154 },
  { label: 'S5', canonical: s5, triples: 139 },
  { label: 'S6', canonical: s6, triples: 150 },
  { label: 'S7', canonical: s7, triples: 173 },
];

/** @type {{ url: string, stop: () => void } | undefined} */
let backend;
let baseUrl = '';

beforeAll(async () => {
  backend = await startBackend({
    NEBULA_API_KEY: 'integration-test-key', NEBULA_MODEL: 'integration-test-model',
  }, 'frontend.integration.nebula_stub:app');
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
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/** Mount the real App against `apiUrl`. */
async function mountApp(apiUrl = baseUrl, structured = true) {
  vi.stubEnv('VITE_API_URL', apiUrl);
  const { default: App } = await import('../src/App.svelte');
  app = mount(App, { target: document.body });
  flushSync();
  if (structured) {
    clickButton('Structured Editor');
    clickButton('Expand all');
  }
}

const text = () => document.body.textContent ?? '';
const interpretationDocument = () => JSON.parse(document.querySelector('pre.json')?.textContent ?? '{}');
const draft = () => interpretationDocument().scenario;
const validationStatus = () => document.querySelector('[data-validation-status]')?.textContent?.trim();

function textOutsideJson() {
  const copy = /** @type {HTMLElement} */ (document.body.cloneNode(true));
  copy.querySelector('pre.json')?.remove();
  return copy.textContent ?? '';
}

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
    if (!condition()) throw new Error(`Condition not met (validation status: ${validationStatus()})`);
  }, { timeout: 15_000, interval: 50 });
}

async function validateScenario() {
  clickButton('Validate Scenario');
  await until(() => validationStatus() === 'Valid');
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

/** @param {string} [id] */
function descriptionInput(id = 'scenario-wizard-answer') {
  const answer = document.getElementById(id);
  if (!(answer instanceof HTMLTextAreaElement)) throw new Error(`No description input "${id}"`);
  return answer;
}

/** @param {string} value @param {string} [id] */
function enterDescription(value, id) {
  const answer = descriptionInput(id);
  answer.value = value;
  answer.dispatchEvent(new Event('input', { bubbles: true }));
  flushSync();
}

/** @param {string} json @param {string} name */
async function importJson(json, name) {
  const input = /** @type {HTMLInputElement} */ (document.querySelector('input[type=file]'));
  Object.defineProperty(input, 'files', { value: [{ name, text: async () => json }], configurable: true });
  input.dispatchEvent(new Event('change', { bubbles: true }));
  await until(() => text().includes(`Loaded ${name}`));
}

async function downloadJson() {
  const createObjectURL = vi.fn((/** @type {Blob} */ _blob) => 'blob:interpretation');
  vi.stubGlobal('URL', class extends URL { static createObjectURL = createObjectURL; static revokeObjectURL = vi.fn(); });
  const download = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  clickButton('Download JSON');
  expect(download).toHaveBeenCalledOnce();
  const blob = createObjectURL.mock.calls[0][0];
  const content = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
  return JSON.parse(String(content));
}

describe('Svelte → FastAPI → RDF → SHACL', () => {
  it('streams unprocessed descriptions to the JSON viewer and retains them across input methods', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    await mountApp(baseUrl, false);
    expect(validationStatus()).toBe('Not validated');
    expect(draft()).toBeNull();

    const description = '  A researcher and an assistant review data.\nTheir roles are undecided.  ';
    enterDescription(description);
    const raw = interpretationDocument();
    expect(raw.source_description.use_case).toBe(description);
    expect(raw.scenario).toBeNull();
    const viewerLink = /** @type {HTMLAnchorElement} */ (document.querySelector('.json-panel a'));
    expect(JSON.parse(await requestScenarioJson(new URL(viewerLink.href).hash.slice(1)))).toEqual(raw);

    clickButton('Next');
    clickButton('Previous');
    clickButton('Structured Editor');
    clickButton('Describe with AI');
    expect(descriptionInput().value).toBe(description);
    expect(interpretationDocument().source_description).toEqual(raw.source_description);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('combines all description inputs in a complete interpretation and validates edits only on request', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    await mountApp(baseUrl, false);
    const source = {
      use_case: 'A personal assistant HI system for health and lifestyle.',
      full_description: '  A human user and an AI assistant collaborate on wellbeing — the goal requires collecting user self-reports and sensor activity data.\nTheir setting is health monitoring.  ',
      additional_notes: '  Sensor noise can affect measurements.\nPrivacy is a constraint.  ',
    };
    enterDescription(source.use_case);
    clickButton('Write full description');
    enterDescription(source.full_description, 'scenario-full-description');
    clickButton('Back to questions');
    expect(descriptionInput().value).toBe(source.use_case);
    clickButton('Add additional notes');
    enterDescription(source.additional_notes, 'scenario-additional-notes');
    clickButton('Back to questions');
    clickButton('Write full description');
    expect(descriptionInput('scenario-full-description').value).toBe(source.full_description);
    const before = interpretationDocument();
    expect(before.source_description).toEqual(source);
    expect(before.scenario).toBeNull();

    clickButton('Convert to JSON using AI');
    expect(text()).toContain('Interpreting description…');
    await until(() => interpretationDocument().interpretation.status === 'complete');
    const interpreted = interpretationDocument();
    expect(interpreted.source_description).toEqual(before.source_description);
    expect(interpreted.interpretation).toMatchObject({
      status: 'complete', model: 'integration-test-model', prompt_version: expect.stringMatching(/\S/),
      source_description: before.source_description,
      generated_scenario: { use_case: legacyExample.use_case, agents: legacyExample.agents },
    });
    expect(interpreted.scenario.goal.required_tasks).toEqual([legacyExample.tasks[0].id]);
    expect(interpreted.scenario.context).toMatchObject({ phenomena: ['SensorNoisePhenomenon'], constraints: ['PrivacyConstraint'] });
    expect(interpreted.scenario).not.toHaveProperty('executions');
    expect(interpreted.scenario.agents.map((/** @type {{ kind: string }} */ agent) => agent.kind).sort()).toEqual(['artificial', 'human']);
    expect(validationStatus()).toBe('Not validated');

    const exported = await downloadJson();
    expect(exported).toEqual(interpreted);
    await importJson(JSON.stringify(exported), 'mixed-description.json');
    expect(interpretationDocument()).toEqual(interpreted);
    clickButton('Describe with AI');
    expect(descriptionInput().value).toBe(source.use_case);
    clickButton('Write full description');
    expect(descriptionInput('scenario-full-description').value).toBe(source.full_description);
    clickButton('Back to questions');
    clickButton('Add additional notes');
    expect(descriptionInput('scenario-additional-notes').value).toBe(source.additional_notes);
    clickButton('Structured Editor');

    const agent = interpreted.scenario.agents.find((/** @type {{ kind: string }} */ choice) => choice.kind === 'human');
    const editor = /** @type {Element} */ (document.getElementById(`agent-${agent.id}`)?.closest('section'));
    enterText(editor, 'Name', 'Research participant');
    const edited = draft();
    expect(edited.agents).toContainEqual({ ...agent, name: 'Research participant' });
    expect(interpretationDocument().interpretation).toMatchObject({
      generated_scenario: interpreted.interpretation.generated_scenario, scenario_changed: true,
    });
    expect(fetchSpy).toHaveBeenCalledOnce();
    expect(fetchSpy.mock.calls[0][0]).toBe(`${baseUrl}/scenarios/interpret`);
    expect(JSON.parse(String(fetchSpy.mock.calls[0][1]?.body))).toEqual({ description: before.source_description });

    await validateScenario();
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    expect(fetchSpy.mock.calls[1][0]).toBe(`${baseUrl}/scenarios/preview`);
    expect(JSON.parse(String(fetchSpy.mock.calls[1][1]?.body))).toEqual(edited);
    const rdfToggle = [...document.querySelectorAll('summary')].find((node) => node.textContent?.trim() === 'RDF preview');
    expect(rdfToggle).toBeDefined();
    rdfToggle?.click();
    flushSync();
    expect(document.querySelector('pre.rdf')?.textContent).toContain('"Research participant"');
    expect(document.querySelector('pre.report')?.textContent).toMatch(/Conforms:\s*True/);

    clickButton('Describe with AI');
    const confirm = vi.fn(() => false);
    vi.stubGlobal('confirm', confirm);
    clickButton('Convert to JSON using AI');
    expect(confirm).toHaveBeenCalledOnce();
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    clickButton('Structured Editor');
    expect(draft()).toEqual(edited);
    expect(validationStatus()).toBe('Valid');
    enterText(/** @type {Element} */ (document.getElementById(`agent-${agent.id}`)?.closest('section')), 'Name', agent.name);
    expect(validationStatus()).toBe('Not validated');
    expect(document.querySelector('pre.rdf')).toBeNull();
    expect(interpretationDocument().source_description).toEqual(before.source_description);
  });

  it('downloads a partial candidate, reports missing facts and validates after structured repair', async () => {
    await mountApp(baseUrl, false);
    enterDescription('A personal assistant HI system for health and lifestyle.');
    clickButton('Next');
    enterDescription('Maintain and improve user wellbeing.');
    clickButton('Next');
    enterDescription('The goal requires collecting user self-reports and sensor-based activity data.');
    clickButton('Next');
    enterDescription('A human user is on the team in the role of user. Other team members are still to be determined.');
    clickButton('Next');
    clickButton('Next');
    enterDescription('In a health-monitoring setting, sensor noise can affect measurements. User privacy is a constraint in this setting.');
    clickButton('Convert to JSON using AI');
    await until(() => interpretationDocument().interpretation.status === 'incomplete');
    const partial = interpretationDocument();
    expect(partial.scenario.agents).toMatchObject([{ kind: 'human', name: 'Human user' }]);
    expect(partial.interpretation.diagnostics).toContainEqual(expect.objectContaining({
      kind: 'missing_information', path: 'agents', message: expect.stringMatching(/artificial/),
    }));
    expect(partial.interpretation.diagnostics).toContainEqual(expect.objectContaining({ kind: 'technical_validation', path: 'agents' }));
    const exported = await downloadJson();
    expect(exported).toEqual(partial);
    await importJson(JSON.stringify(exported), 'partial.json');
    expect(interpretationDocument()).toEqual(partial);

    expect(await requestPreview(partial.scenario, { baseUrl })).toMatchObject({ kind: 'rejected', status: 422 });
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    clickButton('Validate Scenario');
    expect(validationStatus()).toBe('Needs corrections');
    expect(textOutsideJson()).toContain('The team needs at least one human and one artificial agent.');
    expect(fetchSpy).not.toHaveBeenCalled();

    clickButton('Add artificial agent');
    const added = draft().agents.at(-1);
    const editor = /** @type {Element} */ (document.getElementById(`agent-${added.id}`)?.closest('section'));
    enterText(editor, 'Name', 'AI assistant provided by the researcher');
    const role = /** @type {HTMLInputElement} */ (editor.querySelector('input[value="AIAssistantRole"]'));
    role.click();
    flushSync();
    expect(interpretationDocument().source_description).toEqual(partial.source_description);
    expect(draft().agents[0]).toEqual(partial.scenario.agents[0]);
    expect(fetchSpy).not.toHaveBeenCalled();
    await validateScenario();
    expect(document.querySelector('pre.rdf')?.textContent).toContain('"AI assistant provided by the researcher"');
  });

  it('keeps unsupported interpretation findings in JSON without rendering a findings panel', async () => {
    await mountApp(baseUrl, false);
    const description = 'We study precision ranking. Our participants exercise joint authority over the ranking.';
    enterDescription(description);
    clickButton('Convert to JSON using AI');
    await until(() => interpretationDocument().interpretation.status === 'incomplete');

    const result = interpretationDocument();
    expect(result.source_description.use_case).toBe(description);
    expect(result.scenario.use_case).toMatchObject({ name: 'Precision ranking', concept: '' });
    expect(result.scenario).not.toHaveProperty('interactions');
    const vocabularyFinding = 'Consider precision ranking as a vocabulary suggestion.';
    const relationshipFinding = 'The scenario cannot express the proposed joint authority relationship.';
    expect(result.interpretation.diagnostics).toEqual(expect.arrayContaining([
      expect.objectContaining({ kind: 'unsupported_vocabulary', path: 'use_case.concept', message: vocabularyFinding }),
      expect.objectContaining({ kind: 'unsupported_relationship', message: relationshipFinding }),
    ]));
    expect(textOutsideJson()).not.toContain(vocabularyFinding);
    expect(textOutsideJson()).not.toContain(relationshipFinding);
    const headings = [...document.querySelectorAll('h2, h3')].map((heading) => heading.textContent?.trim());
    expect(headings).not.toContain('AI interpretation');
    expect(validationStatus()).toBe('Not validated');

    const exported = await downloadJson();
    expect(exported).toEqual(result);
    await importJson(JSON.stringify(exported), 'findings.json');
    expect(interpretationDocument()).toEqual(result);
    expect(textOutsideJson()).not.toContain(vocabularyFinding);
    expect(textOutsideJson()).not.toContain(relationshipFinding);
  });

  it('reports an empty interpretation briefly and keeps the findings in JSON', async () => {
    await mountApp(baseUrl, false);
    const description = 'The study is still unspecified.';
    const finding = 'Specify the study goal before interpreting it.';
    enterDescription(description);
    clickButton('Convert to JSON using AI');
    await until(() => textOutsideJson().includes('AI interpretation did not produce an editable scenario.'));
    expect(descriptionInput().value).toBe(description);
    expect(draft()).toBeNull();
    expect(interpretationDocument().interpretation.diagnostics).toContainEqual({
      kind: 'missing_information', path: 'goal', message: finding,
    });
    expect(textOutsideJson()).not.toContain(finding);
  });

  it('reports an interpretation failure without exposing provider details or losing the description', async () => {
    await mountApp(baseUrl, false);
    const description = 'Provider temporarily unavailable.';
    enterDescription(description);
    clickButton('Convert to JSON using AI');
    await until(() => Boolean(document.querySelector('[role="alert"]')));
    expect(document.querySelector('[role="alert"]')?.textContent?.trim()).toBe('AI interpretation failed. Try again.');
    expect(text()).not.toContain('Nebula could not complete the interpretation');
    expect(text()).not.toContain('Synthetic upstream provider detail');
    expect(descriptionInput().value).toBe(description);
    expect(interpretationDocument().source_description.use_case).toBe(description);
    expect(draft()).toBeNull();
    expect(validationStatus()).toBe('Not validated');
  });

  it.each(reconstructions)('imports $label, exports it through Copy, reimports it, and previews identical RDF', async ({ canonical, triples }) => {
    await mountApp();
    await importJson(JSON.stringify(canonical), 'example.json');
    expect(draft()).toEqual(canonical);
    const expected = await requestPreview(canonical, { baseUrl });
    expect(expected.kind).toBe('ok');
    if (expected.kind !== 'ok') throw new Error(JSON.stringify(expected));
    await validateScenario();
    expect(text()).toContain(`${triples} triples`);
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
    expect(JSON.parse(exported).scenario).toEqual(canonical);
    unmount(/** @type {Record<string, any>} */ (app));
    app = undefined;
    await mountApp();
    await importJson(exported, 'example.json');
    expect(draft()).toEqual(canonical);
    await validateScenario();
    expect(document.querySelector('pre.rdf')?.textContent).toBe(expected.preview.rdf);
  });

  it.each(reconstructions)('enters the complete $label through the form with independent entities and source relationships', async ({ canonical, triples }) => {
    await mountApp(); // Start with a blank form; do not load or inject scenario JSON.
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
    const useCase = /** @type {Element} */ (document.querySelector('#section-use_case fieldset'));
    enterText(useCase, 'Name', canonical.use_case.name);
    selectValue(useCase, 'Use case type', canonical.use_case.concept);
    selectValue(useCase, 'Domain (optional)', canonical.use_case.domain);
    const goal = /** @type {Element} */ (document.querySelector('#goal-name')?.closest('fieldset'));
    enterText(goal, 'Name', canonical.goal.name);
    selectValue(goal, 'Goal type', canonical.goal.concept);
    if ('team_constraints' in canonical && Array.isArray(canonical.team_constraints)) {
      selectChecks(document, 'Team constraints (optional)', canonical.team_constraints);
    }
    clickButton('Add context');
    selectValue(document, 'Context type', canonical.context.concept);
    selectChecks(document, 'Phenomena', canonical.context.phenomena);
    selectChecks(document, 'Constraints', canonical.context.constraints);
    if ('description' in canonical.context && typeof canonical.context.description === 'string') {
      const context = /** @type {Element} */ (document.querySelector('#context-description')?.closest('fieldset'));
      enterText(context, 'Description in English (optional)', canonical.context.description);
    }
    canonical.tasks.forEach((task, i) => {
      if (i > 0) clickButton('Add task');
      const id = draft().tasks[i].id;
      ids.tasks[task.id] = id;
      const section = /** @type {Element} */ (document.querySelector(`#task-${id}`)?.closest('section'));
      enterText(section, 'Name', task.name);
      selectValue(section, 'Task type', task.concept);
      if ('description' in task && typeof task.description === 'string') enterText(section, 'Description in English (optional)', task.description);
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
        const control = /** @type {HTMLInputElement | null} */ (section.querySelector(`fieldset.roles input[value="${role}"]`));
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
      selectValue(section, 'Hypothesis literal format', 'hypothesis_language' in experiment ? String(experiment.hypothesis_language) : '');
      if ('description' in experiment && typeof experiment.description === 'string') enterText(section, 'Description in English (optional)', experiment.description);
    }
    for (const evaluation of canonical.evaluations) {
      const section = addRecord('evaluation', 'evaluations', evaluation.id);
      selectValue(section, 'Evaluation type', evaluation.concept);
      selectChecks(section, 'Metrics', evaluation.metrics);
      selectValue(section, 'Experiment', ids.experiments[evaluation.experiment]);
      selectChecks(section, 'Evaluated executions', evaluation.executions.map((id) => ids.executions[id]));
      if ('description' in evaluation && typeof evaluation.description === 'string') enterText(section, 'Description in English (optional)', evaluation.description);
    }
    for (const interaction of canonical.interactions) {
      const section = addRecord('interaction', 'interactions', interaction.id);
      selectValue(section, 'Interaction intent', interaction.intent);
      selectValue(section, 'Interaction modality', interaction.modality);
      selectChecks(section, 'Participating agents', interaction.agents.map((id) => ids.agents[id]));
      selectChecks(section, 'Related executions (optional)', interaction.executions.map((id) => ids.executions[id]));
      if ('description' in interaction && typeof interaction.description === 'string') enterText(section, 'Description in English (optional)', interaction.description);
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
      interactions: canonical.interactions.map((interaction) => ({ ...interaction, id: ids.interactions[interaction.id], agents: interaction.agents.map((id) => ids.agents[id]), executions: interaction.executions.map((id) => ids.executions[id]) })),
    };
    expect(new Set(Object.values(ids.agents)).size).toBe(canonical.agents.length);
    expect(entered.agents).toHaveLength(canonical.agents.length);
    // Extra human rows are appended after the initial human/artificial pair; row order is not identity.
    expected.agents.sort((a, b) => entered.agents.findIndex((/** @type {any} */ agent) => agent.id === a.id) - entered.agents.findIndex((/** @type {any} */ agent) => agent.id === b.id));
    expect(entered).toEqual(expected);
    await validateScenario();
    expect(text()).toContain(`${triples} triples`);
    const rdf = document.querySelector('pre.rdf')?.textContent ?? '';
    expect(rdf.match(/<https:\/\/w3id.org\/hi-ontology#requiresTask>/g)).toHaveLength(canonical.goal.required_tasks.length);
    expect(rdf.match(/<https:\/\/w3id.org\/hi-ontology#hasInteractionEpisode>/g) ?? []).toHaveLength(canonical.interactions.reduce((sum, interaction) => sum + interaction.executions.length, 0));
    for (const task of canonical.tasks) {
      if ('description' in task && typeof task.description === 'string') expect(rdf).toContain(`<urn:hi-app:scenario:${entered.id}:task:${ids.tasks[task.id]}> <http://www.w3.org/2000/01/rdf-schema#comment> ${JSON.stringify(task.description)}@en .`);
    }
    if ('description' in canonical.context && typeof canonical.context.description === 'string') expect(rdf).toContain(`<urn:hi-app:scenario:${entered.id}:context> <http://www.w3.org/2000/01/rdf-schema#comment> ${JSON.stringify(canonical.context.description)}@en .`);
    const described = [canonical.context, ...canonical.tasks, ...canonical.experiments, ...canonical.evaluations, ...canonical.interactions]
      .filter((entity) => 'description' in entity && typeof entity.description === 'string');
    expect(rdf.match(/<http:\/\/www.w3.org\/2000\/01\/rdf-schema#comment>/g) ?? []).toHaveLength(described.length);
    for (const experiment of canonical.experiments) {
      const language = 'hypothesis_language' in experiment ? `@${experiment.hypothesis_language}` : '';
      const subject = `<urn:hi-app:scenario:${entered.id}:experiment:${ids.experiments[experiment.id]}>`;
      expect(rdf).toContain(`${subject} <https://w3id.org/hi-ontology#hasNullHypothesis> ${JSON.stringify(experiment.null_hypothesis)}${language} .`);
      expect(rdf).toContain(`${subject} <https://w3id.org/hi-ontology#hasAlternativeHypothesis> ${JSON.stringify(experiment.alternative_hypothesis)}${language} .`);
    }
    const preview = await requestPreview(expected, { baseUrl });
    expect(preview.kind).toBe('ok');
    if (preview.kind !== 'ok') throw new Error(JSON.stringify(preview));
    expect(rdf).toBe(preview.preview.rdf);
  }, 60_000);

  it('keeps Team constraints separate from Context edits and previews them without a Context', async () => {
    await mountApp();
    clickButton('Load S1 example');
    /** @param {string} label */
    const checklist = (label) => {
      const fieldset = [...document.querySelectorAll('fieldset')].find((f) => f.querySelector('legend')?.textContent?.trim() === label);
      if (!fieldset) throw new Error(`No checklist ${label}`);
      return fieldset;
    };
    /** @param {string} label @param {string} concept */
    const toggle = (label, concept) => {
      const control = /** @type {HTMLInputElement} */ (checklist(label).querySelector(`input[value="${concept}"]`));
      control.click();
      flushSync();
    };
    expect(checklist('Team constraints (optional)').querySelectorAll('input:checked')).toHaveLength(0);
    toggle('Team constraints (optional)', 'AccessibilityConstraint');
    expect(draft().context.constraints).toEqual(example.context.constraints);
    toggle('Constraints', 'FairnessConstraint');
    expect(draft().team_constraints).toEqual(['AccessibilityConstraint']);
    toggle('Team constraints (optional)', 'AccessibilityConstraint');
    toggle('Team constraints (optional)', 'PrivacyConstraint');
    expect(draft().context.constraints).toEqual([...example.context.constraints, 'FairnessConstraint']);
    clickButton('Remove context');
    expect(draft()).not.toHaveProperty('context');
    expect(draft().team_constraints).toEqual(['PrivacyConstraint']);
    await validateScenario();
    expect(text()).toContain('117 triples');
    const rdf = document.querySelector('pre.rdf')?.textContent ?? '';
    expect(rdf).toContain('<urn:hi-app:scenario:s1:team> <https://w3id.org/hi-ontology#hasConstraintConcept> <https://w3id.org/hi-thesaurus/PrivacyConstraint> .');
    expect(rdf).not.toContain('<urn:hi-app:scenario:s1:context>');
  });

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
    expect(draft().goal.required_tasks).toEqual(['data-collection']);
    await validateScenario();
    expect(text()).toContain('125 triples');
    let rdf = document.querySelector('pre.rdf')?.textContent ?? '';
    expect(rdf.match(/<https:\/\/w3id.org\/hi-ontology#requiresTask>/g)).toHaveLength(1);
    for (const task of example.tasks) {
      expect(rdf).toContain(`<urn:hi-app:scenario:s1:task:${task.id}> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <https://w3id.org/hi-ontology#Task> .`);
    }
    expect(rdf).toContain('<urn:hi-app:scenario:s1:execution:explanation> <https://w3id.org/hi-ontology#realizesTask> <urn:hi-app:scenario:s1:task:explanation> .');

    clickButton('Add task');
    const beforeTaskEdit = draft();
    const id = beforeTaskEdit.tasks.at(-1).id;
    const taskSection = /** @type {Element} */ (document.querySelector(`#task-${id}`)?.closest('section'));
    enterText(taskSection, 'Name', 'Supporting task');
    selectValue(taskSection, 'Task type', 'DataCollectionTask');
    expect(beforeTaskEdit.goal.required_tasks).toEqual(['data-collection']);
    expect(/** @type {HTMLInputElement} */ (checklist.querySelector(`input[value="${id}"]`)).checked).toBe(false);
    await validateScenario();
    expect(text()).toContain('128 triples');
    rdf = document.querySelector('pre.rdf')?.textContent ?? '';
    expect(rdf).toContain(`<urn:hi-app:scenario:s1:task:${id}> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <https://w3id.org/hi-ontology#Task> .`);
    expect(rdf).not.toContain(`<urn:hi-app:scenario:s1:goal:user-wellbeing> <https://w3id.org/hi-ontology#requiresTask> <urn:hi-app:scenario:s1:task:${id}> .`);
  });

  it('removes task references and blocks validation until an empty requirement selection is repaired', async () => {
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
      expect(draft().goal.required_tasks).toEqual(id === 'conflict-resolution' ? ['data-collection'] : []);
    }
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    try {
      clickButton('Validate Scenario');
      expect(text()).toContain('Choose at least one required task.');
      expect(fetchSpy).not.toHaveBeenCalled();
    } finally { fetchSpy.mockRestore(); }
    const goal = /** @type {Element} */ (document.querySelector('#goal-name')?.closest('fieldset'));
    /** @type {HTMLInputElement} */ (goal.querySelector('input[value="explanation"]')).click();
    flushSync();
    expect(draft().goal.required_tasks).toEqual(['explanation']);
    await validateScenario();
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
    await validateScenario();
    expect(text()).toContain('123 triples'); // Legacy S1 without these comments.

    enterText(goal, 'Description in English (optional)', example.goal.description);
    expect(document.querySelector('pre.rdf')).toBeNull();
    example.tasks.forEach((task, i) => enterText(tasks[i], 'Description in English (optional)', task.description));
    expect(draft()).toEqual(example);
    await validateScenario();
    expect(text()).toContain('127 triples');
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
    expect(draft()).not.toHaveProperty('interactions');
    clickButton('Add interaction');
    const section = /** @type {Element} */ (document.querySelector('[data-interaction-id]'));
    selectValue(section, 'Interaction intent', example.interactions[0].intent);
    selectValue(section, 'Interaction modality', example.interactions[0].modality);
    /** @type {HTMLInputElement} */ (section.querySelector('input[value="explanation"]')).click();
    flushSync();
    expect(draft().interactions[0].agents).toEqual([]);
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    try {
      clickButton('Validate Scenario');
      expect(fetchSpy).not.toHaveBeenCalled();
      expect(text()).toContain('Choose at least two distinct agents.');
    } finally { fetchSpy.mockRestore(); }
    for (const id of example.interactions[0].agents) {
      /** @type {HTMLInputElement} */ (section.querySelector(`input[value="${id}"]`)).click();
      flushSync();
    }
    const entered = draft().interactions[0];
    expect(entered).toMatchObject({ intent: 'ExplanationIntent', modality: 'VerbalDialogueModality', agents: example.interactions[0].agents, executions: ['explanation'] });
    await validateScenario();
    expect(text()).toContain('127 triples');
    /** @type {HTMLInputElement} */ (section.querySelector('input[value="explanation"]')).click();
    flushSync();
    expect(document.querySelector('pre.rdf')).toBeNull();
    await validateScenario();
    expect(text()).toContain('126 triples');
    enterText(section, 'Description in English (optional)', 'User-entered interaction description.');
    const changed = draft().interactions[0];
    expect(changed.id).toBe(entered.id);
    expect(changed.executions).toEqual([]);
    await validateScenario();
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
    expect(draft().interactions).toEqual(data.interactions);
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    try {
      clickButton('Validate Scenario');
      expect(fetchSpy).not.toHaveBeenCalled();
    } finally { fetchSpy.mockRestore(); }
    const interaction = /** @type {Element} */ (document.querySelector('[data-interaction-id]'));
    const replacement = kind === 'agent' ? 'replacement-human' : 'conflict-resolution';
    /** @type {HTMLInputElement} */ (interaction.querySelector(`input[value="${replacement}"]`)).click();
    flushSync();
    /** @type {HTMLInputElement} */ (interaction.querySelector(`input[value="${id}"]`)).click();
    flushSync();
    const repaired = draft().interactions[0];
    expect(repaired.id).toBe(data.interactions[0].id);
    expect(repaired.description).toBe(data.interactions[0].description);
    await validateScenario();
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
    const created = /** @type {import('../src/lib/scenario.js').Scenario} */ (draft());
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
    const entered = /** @type {import('../src/lib/scenario.js').Scenario} */ (draft());
    expect(entered.experiments.map(({ id, ...facts }) => facts)).toEqual(example.experiments.map(({ id, ...facts }) => facts));
    expect(entered.evaluations.map(({ id, experiment, ...facts }) => facts)).toEqual(example.evaluations.map(({ id, experiment, ...facts }) => facts));
    await validateScenario();
    expect(text()).toContain('127 triples');
    const firstExperiment = /** @type {Element} */ (document.querySelector('[data-experiment-id]'));
    selectValue(firstExperiment, 'Hypothesis literal format', 'en');
    expect(document.querySelector('pre.rdf')).toBeNull();
    await validateScenario();
    expect(document.querySelector('pre.rdf')?.textContent).toContain(`"${example.experiments[0].null_hypothesis}"@en`);
    const firstEvaluation = /** @type {Element} */ (document.querySelector('[data-evaluation-id]'));
    for (const section of [firstExperiment, firstEvaluation]) {
      /** @type {HTMLInputElement} */ (section.querySelector('input[value="FairOutcomeMetric"]')).click();
      flushSync();
    }
    /** @type {HTMLInputElement} */ (firstEvaluation.querySelector('input[value="conflict-resolution"]')).click();
    flushSync();
    await validateScenario();
    expect(text()).toContain('130 triples');
  });

  it.each(['experiment', 'execution'])('keeps evaluation data when a referenced %s is deleted and supports repair', async (kind) => {
    await mountApp();
    clickButton('Load S1 example');
    const id = kind === 'experiment' ? 'data-collection-quality' : 'data-collection';
    document.querySelector(`[data-${kind}-id="${id}"] button`)?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    flushSync();
    expect(draft().evaluations).toEqual(example.evaluations);
    expect(text()).toContain(kind === 'experiment' ? `"${id}" no longer exists` : `Referenced records no longer exist: ${id}`);
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    try {
      clickButton('Validate Scenario');
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
    const repaired = draft().evaluations[0];
    expect(repaired.id).toBe(example.evaluations[0].id);
    expect(repaired.description).toBe(example.evaluations[0].description);
    await validateScenario();
  });

  it('enters all S1 executions through the form and supports optional methods', async () => {
    await mountApp();
    clickButton('Load S1 example');
    clickButton('Remove interaction');
    for (const _ of example.evaluations) clickButton('Remove evaluation');
    for (const _ of example.experiments) clickButton('Remove experiment');
    for (const _ of example.executions) clickButton('Remove execution');
    expect(draft()).not.toHaveProperty('executions');
    for (const execution of example.executions) {
      clickButton('Add execution');
      const section = document.querySelectorAll('[data-execution-id]').item(document.querySelectorAll('[data-execution-id]').length - 1);
      selectValue(section, 'Execution type', execution.concept);
      selectValue(section, 'Task', execution.task);
      selectValue(section, 'Agent', execution.agent);
      selectValue(section, 'Method (optional)', execution.method);
    }
    const entered = /** @type {import('../src/lib/scenario.js').Scenario} */ (draft());
    expect(entered.executions.map(({ id, ...facts }) => facts)).toEqual(example.executions.map(({ id, ...facts }) => facts));
    expect(new Set(entered.executions.map((e) => e.id)).size).toBe(3);
    await validateScenario();
    expect(text()).toContain('88 triples');
    selectValue(/** @type {Element} */ (document.querySelector('[data-execution-id]')), 'Method (optional)', '');
    expect(document.querySelector('pre.rdf')).toBeNull();
    expect(draft().executions[0]).not.toHaveProperty('method');
    await validateScenario();
    expect(text()).toContain('87 triples');
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
    expect(draft().executions).toEqual(data.executions);
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    try {
      clickButton('Validate Scenario');
      expect(fetchSpy).not.toHaveBeenCalled();
    } finally {
      fetchSpy.mockRestore();
    }
    const execution = /** @type {Element} */ (document.querySelector('[data-execution-id="data-collection"]'));
    selectValue(execution, kind === 'agent' ? 'Agent' : 'Task', kind === 'agent' ? 'replacement-human' : 'explanation');
    expect(text()).not.toContain(`"${id}" no longer exists`);
    const repaired = draft().executions[0];
    expect(repaired.id).toBe(data.executions[0].id);
    expect(repaired.method).toBe(data.executions[0].method);
    await validateScenario();
  });

  it('enters all four S1 capabilities through the form and shares their references', async () => {
    await mountApp();
    clickButton('Load S1 example');
    for (const _ of example.capabilities) clickButton('Remove capability');
    expect(draft()).not.toHaveProperty('capabilities');
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
    const entered = /** @type {import('../src/lib/scenario.js').Scenario} */ (draft());
    expect(entered.capabilities.map(({ id, ...facts }) => facts)).toEqual(example.capabilities.map(({ id, ...facts }) => facts));
    expect(new Set(entered.capabilities.map((c) => c.id)).size).toBe(4);
    await validateScenario();
    expect(text()).toContain('127 triples');

    const first = document.querySelector('[data-capability-id]');
    for (const id of ['human-user', 'conflict-resolution']) {
      /** @type {HTMLInputElement} */ (first?.querySelector(`input[value="${id}"]`)).click();
      flushSync();
    }
    const changed = draft().capabilities[0];
    expect(changed.id).toBe(entered.capabilities[0].id);
    expect(changed.agents).toEqual(['ai-assistant', 'human-user']);
    expect(changed.tasks).toEqual(['data-collection', 'conflict-resolution']);
    expect(document.querySelector('pre.rdf')).toBeNull();
    await validateScenario();
    expect(text()).toContain('130 triples');
  });

  it('enters the complete original S1 Context through the form', async () => {
    await mountApp();
    clickButton('Load S1 example');
    clickButton('Remove context');
    expect(draft()).not.toHaveProperty('context');
    clickButton('Add context');
    clickButton('Validate Scenario');
    expect(text()).toContain('Choose a concept.');

    const label = [...document.querySelectorAll('label')].find((l) => l.textContent?.trim() === 'Context type');
    const select = /** @type {HTMLSelectElement} */ (label?.control);
    select.value = example.context.concept;
    select.dispatchEvent(new Event('change', { bubbles: true }));
    flushSync();
    for (const id of [...example.context.phenomena, ...example.context.constraints]) {
      const checkbox = document.querySelector(`#section-context input[value="${id}"]`);
      expect(checkbox, `HINT option ${id}`).not.toBeNull();
      /** @type {HTMLInputElement} */ (checkbox).click();
      flushSync();
    }
    const description = /** @type {HTMLTextAreaElement} */ (document.querySelector('#context-description'));
    description.value = example.context.description;
    description.dispatchEvent(new Event('input', { bubbles: true }));
    flushSync();
    expect(draft().context).toEqual(example.context);

    await validateScenario();
    expect(text()).toContain('127 triples');
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
    expect(draft()).toEqual(example);
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
    await validateScenario();
    expect(text()).toContain('127 triples');
    expect(document.querySelector('pre.rdf')?.textContent).toBe(expected);

    const name = /** @type {HTMLInputElement} */ (document.querySelector('#agent-human-user'));
    name.value = 'Renamed participant';
    name.dispatchEvent(new Event('input', { bubbles: true }));
    flushSync();
    expect(validationStatus()).toBe('Not validated');
    expect(document.querySelector('pre.rdf')).toBeNull();

    await validateScenario();
    expect(document.querySelector('pre.rdf')?.textContent).toContain(
      '<urn:hi-app:scenario:s1:agent:human-user> <http://www.w3.org/2000/01/rdf-schema#label> "Renamed participant" .',
    );
  }, 30_000);

  it('blocks incomplete forms locally without calling the backend', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    await mountApp();
    clickButton('Validate Scenario');
    expect(validationStatus()).toBe('Needs corrections');
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it('shows an unavailable backend in the UI', async () => {
    await mountApp(`http://127.0.0.1:${await closedPort()}`);
    clickButton('Load S1 example');
    clickButton('Validate Scenario');
    await until(() => validationStatus() === 'Technical validation error');
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
