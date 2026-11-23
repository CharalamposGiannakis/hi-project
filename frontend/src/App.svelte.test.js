// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';
import App from './App.svelte';
import s5 from '../../examples/s5.json';
import s7 from '../../examples/s7.json';
import { requestScenarioJson } from './lib/json-viewer-channel.js';

/** @type {Record<string, any> | undefined} */
let app;
afterEach(async () => {
  if (app) await unmount(app);
  app = undefined;
  document.body.innerHTML = '';
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function render() {
  app = mount(App, { target: document.body });
  flushSync();
}
const sections = () => [...document.querySelectorAll('details.editor-section')].map((element) => /** @type {HTMLDetailsElement} */ (element));
/** @param {string} id */
const section = (id) => /** @type {HTMLDetailsElement} */ (document.getElementById(`section-${id}`));
const jsonNode = () => /** @type {HTMLPreElement} */ (document.querySelector('pre.json'));
const draft = () => JSON.parse(jsonNode().textContent ?? '{}');
const candidate = () => draft().scenario;
const validationStatus = () => document.querySelector('[data-validation-status]')?.textContent;
const descriptionInput = () => /** @type {HTMLTextAreaElement} */ (document.getElementById('scenario-wizard-answer'));
const fullDescriptionInput = () => /** @type {HTMLTextAreaElement} */ (document.getElementById('scenario-full-description'));
const notesInput = () => /** @type {HTMLTextAreaElement} */ (document.getElementById('scenario-additional-notes'));
const useCaseName = () => /** @type {HTMLInputElement} */ (document.getElementById('use-case-name'));

/** @param {string} id @param {string} value */
function selectValue(id, value) {
  const input = document.getElementById(id);
  if (!(input instanceof HTMLSelectElement)) throw new Error(`No select: ${id}`);
  input.value = value;
  input.dispatchEvent(new Event('change', { bubbles: true }));
  flushSync();
}

function textOutsideJson() {
  const body = /** @type {HTMLBodyElement} */ (document.body.cloneNode(true));
  body.querySelector('pre.json')?.remove();
  return body.textContent ?? '';
}
/** @param {string} label */
function click(label) {
  const control = [...document.querySelectorAll('button')].find((button) => button.textContent?.trim() === label);
  if (!control) throw new Error(`No button: ${label}`);
  control.click();
  flushSync();
}
/** @param {() => void} assertion */
async function until(assertion) {
  await vi.waitFor(() => { flushSync(); assertion(); });
}
/** @param {object} data */
async function importJson(data) {
  const input = /** @type {HTMLInputElement} */ (document.querySelector('input[type=file]'));
  Object.defineProperty(input, 'files', { configurable: true, value: [{ name: 'scenario.json', text: async () => JSON.stringify(data) }] });
  input.dispatchEvent(new Event('change', { bubbles: true }));
  await until(() => expect(document.body.textContent).toContain('Loaded scenario.json'));
}
/** @param {HTMLInputElement | HTMLTextAreaElement} input @param {string} value */
function enter(input, value) {
  input.value = value;
  input.dispatchEvent(new Event('input', { bubbles: true }));
  flushSync();
}

/** Wait for the native details toggle event as well as Svelte's effects. */
async function settleDisclosure() {
  await new Promise((resolve) => setTimeout(resolve, 20));
  flushSync();
}

describe('Scenario Builder navigation', () => {
  it('starts compact, exposes native disclosure state, and expands/collapses every section', async () => {
    render();
    expect(document.getElementById('description-panel')?.hasAttribute('hidden')).toBe(false);
    expect(document.getElementById('structured-panel')?.hasAttribute('hidden')).toBe(true);
    click('Structured Editor');
    expect(sections()).toHaveLength(11);
    expect(sections().filter((element) => element.open).map((element) => element.id)).toEqual(['section-use_case']);
    const summary = section('tasks').querySelector('summary');
    expect(summary?.getAttribute('aria-expanded')).toBe('false');
    expect(summary?.getAttribute('aria-controls')).toBe('section-body-tasks');
    summary?.click();
    await until(() => expect(summary?.getAttribute('aria-expanded')).toBe('true'));
    expect(section('tasks').open).toBe(true);
    click('Expand all');
    expect(sections().every((element) => element.open)).toBe(true);
    click('Collapse all');
    expect(sections().every((element) => !element.open)).toBe(true);
  });

  it.each([{ label: 'S5', canonical: s5 }, { label: 'S7', canonical: s7 }])('imports and edits $label while preserving DOM, IDs, selections, and references across collapses', async ({ canonical }) => {
    render();
    await importJson(canonical);
    expect(candidate()).toEqual(canonical);
    expect(section('tasks').querySelector('.count')?.textContent).toBe(String(canonical.tasks.length));
    expect(section('agents').querySelector('.count')?.textContent).toBe(String(canonical.agents.length));
    click('Expand all');
    const task = canonical.tasks.at(-1);
    if (!task) throw new Error('Example requires tasks');
    const input = /** @type {HTMLInputElement} */ (document.getElementById(`task-${task.id}`));
    enter(input, 'Renamed research task');
    const agent = canonical.agents[0];
    enter(/** @type {HTMLInputElement} */ (document.getElementById(`agent-${agent.id}`)), 'Research participant');
    const expected = structuredClone(canonical);
    expected.tasks[expected.tasks.length - 1].name = 'Renamed research task';
    expected.agents[0].name = 'Research participant';
    const before = jsonNode().textContent;
    for (let pass = 0; pass < 2; pass++) {
      click('Collapse all');
      expect(jsonNode().textContent).toBe(before);
      click('Expand all');
    }
    expect(document.getElementById(`task-${task.id}`)).toBe(input);
    expect(input.value).toBe('Renamed research task');
    expect(candidate()).toEqual(expected);
    expect(document.querySelectorAll('input:checked').length).toBeGreaterThan(10);
  });

  it('reveals all sections containing local validation errors on every validation request', () => {
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    render();
    click('Structured Editor');
    click('Collapse all');
    click('Validate Scenario');
    expect(validationStatus()).toBe('Needs corrections');
    expect(sections().filter((element) => element.open).map((element) => element.id)).toEqual([
      'section-use_case', 'section-goal', 'section-tasks', 'section-agents',
    ]);
    expect(section('agents').querySelector('.error-count')?.textContent).toContain('issues');
    click('Collapse all');
    click('Validate Scenario');
    expect(section('agents').open).toBe(true);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('keeps erroneous sections manually collapsed across native toggle events, unrelated edits, and error resolution', async () => {
    render();
    click('Structured Editor');
    click('Validate Scenario');
    const before = jsonNode().textContent;
    section('tasks').querySelector('summary')?.click();
    await settleDisclosure();
    expect(section('tasks').open).toBe(false);
    expect(section('tasks').querySelector('summary')?.getAttribute('aria-expanded')).toBe('false');
    expect(jsonNode().textContent).toBe(before);
    enter(/** @type {HTMLInputElement} */ (document.getElementById('use-case-name')), 'Unrelated edit');
    await settleDisclosure();
    expect(section('tasks').open).toBe(false);
    click('Collapse all');
    await settleDisclosure();
    expect(sections().every((element) => !element.open)).toBe(true);
    // Clearing one issue does not reopen this or another manually collapsed section.
    enter(/** @type {HTMLInputElement} */ (document.getElementById('goal-name')), 'Team goal');
    await settleDisclosure();
    expect(sections().every((element) => !element.open)).toBe(true);
    click('Validate Scenario');
    await settleDisclosure();
    expect(section('tasks').open).toBe(true);
    expect(section('goal').open).toBe(true);
  });

  it('reveals a newly introduced error even when the section error count stays the same', async () => {
    render();
    await importJson(s7);
    const first = /** @type {HTMLInputElement} */ (document.getElementById(`task-${s7.tasks[0].id}`));
    const second = /** @type {HTMLInputElement} */ (document.getElementById(`task-${s7.tasks[1].id}`));
    enter(first, '');
    expect(section('tasks').open).toBe(true);
    click('Collapse all');
    await settleDisclosure();
    expect(section('tasks').open).toBe(false);
    // Apply a validation transition in one reactive turn: one issue resolved,
    // another introduced. A count-only dependency would miss this change.
    flushSync(() => {
      first.value = s7.tasks[0].name;
      first.dispatchEvent(new Event('input', { bubbles: true }));
      second.value = '';
      second.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await settleDisclosure();
    expect(section('tasks').open).toBe(true);
    expect(section('tasks').querySelector('.error-count')?.textContent?.trim()).toBe('1 issue');
    expect(section('executions').open).toBe(false);
    section('tasks').querySelector('summary')?.click();
    await settleDisclosure();
    expect(section('tasks').open).toBe(false);
  });

  it('reveals nested optional entities and newly broken references, and focuses error destinations', async () => {
    render();
    await importJson(s7);
    click('Expand all');
    click('Add capability');
    click('Add execution');
    click('Add experiment');
    click('Add evaluation');
    click('Add interaction');
    click('Collapse all');
    click('Validate Scenario');
    for (const id of ['capabilities', 'executions', 'experiments', 'evaluations', 'interactions']) {
      expect(section(id).open).toBe(true);
      expect(section(id).querySelector('.error-count')).not.toBeNull();
    }
    click('Collapse all');
    const link = [...document.querySelectorAll('.issues button')].find((button) => button.textContent?.includes('experiments.1.null_hypothesis'));
    if (!(link instanceof HTMLButtonElement)) throw new Error('Missing nested issue link');
    link.click();
    const experimentId = candidate().experiments[1].id;
    await until(() => expect(document.activeElement).toBe(document.getElementById(`null-hypothesis-${experimentId}`)));
    expect(section('experiments').open).toBe(true);

  });

  it('actually removes a referenced S7 agent and reveals the broken execution and interaction references', async () => {
    const data = structuredClone(s7);
    data.agents.push({ ...data.agents[0], id: 'additional-visitor', name: 'Additional visitor' });
    render();
    await importJson(data);
    click('Collapse all');
    section('agents').querySelector('summary')?.click();
    await settleDisclosure();
    const removedId = s7.agents[0].id;
    const agent = document.getElementById(`agent-${removedId}`)?.closest('.item');
    const remove = /** @type {HTMLButtonElement} */ (agent?.querySelector('button'));
    expect(remove.disabled).toBe(false);
    remove.click();
    flushSync();
    await settleDisclosure();
    expect(candidate().agents).toHaveLength(2);
    expect(candidate().agents.some((/** @type {{id: string}} */ agent) => agent.id === removedId)).toBe(false);
    expect(document.getElementById(`agent-${removedId}`)).toBeNull();
    expect(candidate().executions[0].agent).toBe(removedId);
    expect(candidate().interactions[0].agents).toContain(removedId);
    expect(section('executions').open).toBe(true);
    expect(section('interactions').open).toBe(true);
    expect(section('executions').textContent).toContain(`Agent "${removedId}" no longer exists`);
    expect(section('interactions').textContent).toContain(`Unknown agent ID: ${removedId}`);
    expect(document.querySelector('.issues')?.textContent).toContain('executions.0.agent');
    expect(document.querySelector('.issues')?.textContent).toContain('interactions.0.agents');
  });

  it('opens sections for backend validation locations and clears stale feedback after editing', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      code: 'invalid_request', message: 'Invalid input.', shacl_report: null,
      issues: [
        { location: ['body', 'experiments', 0, 'null_hypothesis'], message: 'Review this hypothesis.', type: 'value_error' },
        { location: ['body', 'context', 'phenomena', 0], message: 'Review this phenomenon.', type: 'value_error' },
        { location: ['body', 'team_constraints', 0], message: 'Review this constraint.', type: 'value_error' },
      ],
    }), { status: 422 })));
    render();
    await importJson(s7);
    click('Collapse all');
    click('Validate Scenario');
    await until(() => expect(section('experiments').open).toBe(true));
    expect(validationStatus()).toBe('Needs corrections');
    expect(section('context').open).toBe(true);
    expect(section('team_constraints').open).toBe(true);
    expect(section('tasks').open).toBe(false);
    expect(section('experiments').textContent).toContain('Review this hypothesis.');
    const input = /** @type {HTMLTextAreaElement} */ (document.getElementById(`null-hypothesis-${s7.experiments[0].id}`));
    enter(input, 'Revised hypothesis');
    expect(document.querySelector('.issues')).toBeNull();
    expect(section('experiments').querySelector('.error-count')).toBeNull();
  });

  it('navigates repeated entities, indexed checklists, and section/root errors without guessing fields', async () => {
    const paths = [
      ['body', 'tasks', 2, 'name'], ['body', 'executions', 4, 'agent'],
      ['body', 'context', 'phenomena', 1], ['body', 'team_constraints', 1],
      ['body', 'agents', 1, 'roles', 0], ['body', 'goal', 'required_tasks', 2],
      ['body', 'experiments', 0, 'id'], ['body', 'evaluations', 0, 'unknown_field'],
      ['body', 'interactions'], ['body'], ['body', 'unknown_section', 'name'],
    ];
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      code: 'invalid_request', message: 'Review the fields.', shacl_report: null,
      issues: paths.map((location) => ({ location, message: 'Review this value.', type: 'value_error' })),
    }), { status: 422 })));
    render();
    await importJson(s7);
    click('Validate Scenario');
    await until(() => expect(document.querySelector('.issues')?.textContent).toContain('tasks.2.name'));
    const destinations = [
      ['tasks.2.name', `#task-${s7.tasks[2].id}`],
      ['executions.4.agent', '[data-field-path="executions.4.agent"] select'],
      ['context.phenomena.1', '#section-context input[value="KnowledgeMismatchPhenomenon"]'],
      ['team_constraints.1', '#section-team_constraints input[value="TransparencyConstraint"]'],
      ['agents.1.roles.0', '[data-field-path="agents.1.roles"] input[value="VirtualGuideRole"]'],
      ['goal.required_tasks.2', '#section-goal input[value="compute-similarity"]'],
      ['experiments.0.id', '[data-experiment-id="vr-guide-effectiveness"]'],
      ['evaluations.0.unknown_field', '[data-evaluation-id="vr-guide-impact"]'],
      ['interactions', '#section-interactions > summary'],
    ];
    // Use the navigable issue list in the actions pane, not backend report text.
    const summaryList = document.querySelector('aside > .issues');
    expect(summaryList).not.toBeNull();
    const scroll = vi.fn();
    for (const [path, selector] of destinations) {
      click('Collapse all');
      await settleDisclosure();
      const target = document.querySelector(selector);
      expect(target, path).not.toBeNull();
      Object.defineProperty(target, 'scrollIntoView', { configurable: true, value: scroll });
      scroll.mockClear();
      const link = [...(summaryList?.querySelectorAll('button') ?? [])].find((button) => button.querySelector('code')?.textContent === path);
      if (!(link instanceof HTMLButtonElement)) throw new Error(`Missing issue link: ${path}`);
      link.click();
      await until(() => expect(document.activeElement, path).toBe(target));
      expect(target?.closest('details.editor-section')?.hasAttribute('open')).toBe(true);
      expect(scroll).toHaveBeenCalledWith({ block: 'nearest' });
    }
    expect(summaryList?.textContent).toContain('scenario');
    expect(summaryList?.textContent).toContain('unknown_section.name');
    expect(summaryList?.querySelectorAll('button')).toHaveLength(destinations.length);
    // Indexed array errors also describe the field accessibly.
    const checkbox = /** @type {HTMLInputElement} */ (document.querySelector('#section-context input[value="KnowledgeMismatchPhenomenon"]'));
    const description = document.getElementById(checkbox.getAttribute('aria-describedby') ?? '');
    expect(description?.textContent).toContain('Review this value.');
    const name = document.getElementById(`task-${s7.tasks[2].id}`);
    expect(document.getElementById(name?.getAttribute('aria-describedby') ?? '')?.textContent).toContain('Review this value.');
    expect(candidate()).toEqual(s7);
  });

  it('keeps navigation indexes correct after an earlier repeated entity is removed', async () => {
    render();
    await importJson(s7);
    click('Expand all');
    enter(/** @type {HTMLInputElement} */ (document.getElementById(`task-${s7.tasks[2].id}`)), '');
    document.getElementById(`task-${s7.tasks[0].id}`)?.closest('.item')?.querySelector('button')?.click();
    flushSync();
    click('Collapse all');
    const link = [...document.querySelectorAll('aside > .issues button')].find((button) => button.querySelector('code')?.textContent === 'tasks.1.name');
    if (!(link instanceof HTMLButtonElement)) throw new Error('Missing reindexed issue link');
    link.click();
    await until(() => expect(document.activeElement).toBe(document.getElementById(`task-${s7.tasks[2].id}`)));
  });

  it('ignores validation feedback returned for a scenario edited during the request', async () => {
    /** @type {(response: Response) => void} */
    let respond = () => {};
    vi.stubGlobal('fetch', vi.fn(() => new Promise((resolve) => { respond = resolve; })));
    render();
    await importJson(s7);
    click('Collapse all');
    click('Validate Scenario');
    enter(/** @type {HTMLInputElement} */ (document.getElementById('use-case-name')), 'Updated museum guide');
    respond(new Response(JSON.stringify({
      code: 'invalid_request', message: 'Old validation result.', shacl_report: null,
      issues: [{ location: ['body', 'experiments', 0, 'null_hypothesis'], message: 'Old hypothesis error.', type: 'value_error' }],
    }), { status: 422 }));
    await until(() => expect(document.body.textContent).toContain('The scenario has changed.'));
    expect(validationStatus()).toBe('Not validated');
    expect(section('experiments').open).toBe(false);
    expect(document.querySelector('.issues')).toBeNull();
  });
});

describe('Scenario JSON and validation workflows', () => {
  it('opens an isolated, reloadable viewer URL and serves current unsaved form data without changing the editor', async () => {
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    render();
    await importJson(s7);
    click('Collapse all');
    const sidebar = document.querySelector('.sidebar');
    const pre = jsonNode();
    const link = /** @type {HTMLAnchorElement} */ (document.querySelector('.json-panel a'));
    expect(link.textContent).toBe('Open JSON in new tab');
    expect(link.target).toBe('_blank');
    expect(link.rel).toContain('noopener');
    expect(link.rel).toContain('noreferrer');
    const url = new URL(link.href);
    expect(url.pathname).toBe('/json-viewer.html');
    expect(url.search).toBe('');
    expect(url.hash).not.toContain(s7.id);
    const snapshot = await requestScenarioJson(url.hash.slice(1));
    expect(JSON.parse(snapshot).scenario).toEqual(s7);
    enter(/** @type {HTMLInputElement} */ (document.getElementById('use-case-name')), 'Unsaved museum edits');
    expect(JSON.parse(snapshot).scenario).toEqual(s7);
    const latest = JSON.parse(await requestScenarioJson(url.hash.slice(1)));
    expect(latest.scenario).toEqual({ ...s7, use_case: { ...s7.use_case, name: 'Unsaved museum edits' } });
    expect(document.querySelector('.sidebar')).toBe(sidebar);
    expect(jsonNode()).toBe(pre);
    expect(sections().every((element) => !element.open)).toBe(true);
    expect(fetch).not.toHaveBeenCalled();

    await unmount(/** @type {Record<string, any>} */ (app));
    app = undefined;
    document.body.innerHTML = '';
    render();
    const next = /** @type {HTMLAnchorElement} */ (document.querySelector('.json-panel a'));
    expect(new URL(next.href).hash).not.toBe(url.hash);
  });

  it('keeps the editor usable when separate-tab communication is unavailable', () => {
    vi.stubGlobal('BroadcastChannel', undefined);
    render();
    expect(document.querySelector('.json-panel a')).toBeNull();
    expect(document.body.textContent).toContain('Use Copy or Download JSON instead');
    expect(document.getElementById('use-case-name')).not.toBeNull();
    expect(jsonNode()).not.toBeNull();
    const labels = [...document.querySelectorAll('button')].map((button) => button.textContent?.trim());
    expect(labels).toEqual(expect.arrayContaining(['Copy', 'Download JSON', 'Validate Scenario']));
    expect(labels).not.toContain('Save to GraphDB');
  });

  it('preserves the inline read-only JSON and Copy/Download workflows', async () => {
    const clipboard = vi.fn(async (/** @type {string} */ value) => { void value; });
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: clipboard } });
    const createObjectURL = vi.fn(() => 'blob:test-json');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', class extends URL { static createObjectURL = createObjectURL; static revokeObjectURL = revokeObjectURL; });
    const download = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    render();
    await importJson(s7);
    const pre = jsonNode();
    expect(document.querySelectorAll('pre.json')).toHaveLength(1);
    expect(jsonNode()).toBe(pre);
    expect(pre.tabIndex).toBe(0);
    expect(pre.hasAttribute('contenteditable')).toBe(false);
    expect(document.querySelector('textarea[aria-label*="JSON"]')).toBeNull();
    click('Copy');
    await until(() => expect(document.body.textContent).toContain('JSON copied to the clipboard.'));
    expect(JSON.parse(clipboard.mock.calls[0][0])).toEqual(draft());
    click('Download JSON');
    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(download).toHaveBeenCalledOnce();
    expect(/** @type {HTMLAnchorElement} */ (download.mock.contexts[0]).download).toBe('scenario-s7-draft.json');
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:test-json');
    expect(document.body.textContent).toContain('JSON downloaded to your computer.');
    expect(jsonNode()).toBe(pre);
    expect(candidate()).toEqual(s7);
    click('Download canonical JSON');
    expect(/** @type {HTMLAnchorElement} */ (download.mock.contexts[1]).download).toBe('scenario-s7.json');
    Reflect.deleteProperty(navigator, 'clipboard');
  });

  it('preserves validation while inspecting or editing source text and invalidates it on a scenario edit', async () => {
    const validation = { conforms: true, report: 'Conforms: True' };
    const fetch = vi.fn(async (/** @type {string} */ _url, /** @type {RequestInit} */ _request) => new Response(JSON.stringify({
      scenario_id: 's7', rdf_format: 'nt', rdf: '<urn:s7> <urn:p> "test" .', triple_count: 173, validation,
    })));
    vi.stubGlobal('fetch', fetch);
    render();
    await importJson(s7);
    expect(validationStatus()).toBe('Not validated');
    click('Validate Scenario');
    await until(() => expect(validationStatus()).toBe('Valid'));
    click('Expand all');
    click('Collapse all');
    click('Describe with AI');
    enter(/** @type {HTMLTextAreaElement} */ (document.getElementById('scenario-wizard-answer')), 'Research notes about the museum guide');
    click('Structured Editor');
    expect(document.querySelector('.json-panel a')?.getAttribute('target')).toBe('_blank');
    expect(validationStatus()).toBe('Valid');
    expect(document.body.textContent).toContain('173 triples');
    expect(document.querySelector('pre.rdf')).not.toBeNull();
    expect(fetch).toHaveBeenCalledOnce();
    expect(JSON.parse(String(fetch.mock.calls[0][1].body))).toEqual(s7);
    const name = /** @type {HTMLInputElement} */ (document.getElementById('use-case-name'));
    enter(name, `${s7.use_case.name} `);
    expect(candidate()).toEqual(s7);
    expect(validationStatus()).toBe('Not validated');
    enter(name, s7.use_case.name);
    expect(document.querySelector('pre.rdf')).toBeNull();
    expect(validationStatus()).toBe('Not validated');
  });

});

const modelFindings = /** @type {import('./lib/interpretation.js').ModelInterpretation} */ ({
  status: 'complete', model: 'test-model', prompt_version: 'test-v1', prompt_sha256: 'c'.repeat(64), diagnostics: [],
});

/** @param {Record<string, unknown> | null} scenario @param {typeof modelFindings} findings */
function interpretationReply(scenario, findings = modelFindings) {
  return new Response(JSON.stringify({ scenario, interpretation: findings }));
}

function pendingInterpretation() {
  /** @type {(response: Response) => void} */
  let respond = () => {};
  const fetch = vi.fn(/** @type {typeof globalThis.fetch} */ (() => new Promise((resolve) => { respond = resolve; })));
  vi.stubGlobal('fetch', fetch);
  return { fetch, respond: (/** @type {Response} */ response) => respond(response) };
}

describe('AI interpretation', () => {
  it('interprets all description fields and retains the generated draft when a missing agent kind is corrected', async () => {
    const { fetch, respond } = pendingInterpretation();
    const sourceDescription = {
      use_case: '  A virtual museum guide uses immersive displays.\n',
      full_description: '  Visitors consult a guide.\nA curator oversees the process.  ',
      additional_notes: '  The guide kind is unresolved.\n',
    };
    const generated = { ...s7, agents: [s7.agents[0], { ...s7.agents[1], kind: '' }] };
    const diagnostics = /** @type {typeof modelFindings.diagnostics} */ ([
      { kind: 'missing_information', path: 'agents.1.kind', message: 'The description did not specify the guide kind.' },
    ]);
    render();
    enter(descriptionInput(), sourceDescription.use_case);
    click('Write full description');
    enter(fullDescriptionInput(), sourceDescription.full_description);
    click('Add additional notes');
    enter(notesInput(), sourceDescription.additional_notes);
    expect(draft().source_description).toEqual(sourceDescription);
    expect(candidate()).toBeNull();
    expect(fetch).not.toHaveBeenCalled();

    click('Convert to JSON using AI');
    expect(document.body.textContent).toContain('Interpreting description…');
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/scenarios/interpret'), expect.objectContaining({
      method: 'POST', body: JSON.stringify({ description: sourceDescription }),
    }));
    respond(interpretationReply(generated, { ...modelFindings, status: 'incomplete', diagnostics }));
    await until(() => expect(document.getElementById('structured-panel')?.hasAttribute('hidden')).toBe(false));
    expect(validationStatus()).toBe('Not validated');
    expect(draft().interpretation).toEqual({
      ...modelFindings, status: 'incomplete', diagnostics, source_description: sourceDescription, generated_scenario: generated,
    });
    expect(candidate().agents[1].kind).toBe('');
    const interfaceText = textOutsideJson();
    expect(interfaceText).toContain('Technical validation');
    expect(interfaceText).not.toContain('AI interpretation');
    expect(interfaceText).not.toContain('Missing information');
    expect(interfaceText).not.toContain(diagnostics[0].path);
    expect(interfaceText).not.toContain(diagnostics[0].message);
    expect(interfaceText).not.toContain(modelFindings.model);
    expect(interfaceText).not.toContain(modelFindings.prompt_version);
    expect(interfaceText).not.toContain(modelFindings.prompt_sha256);

    click('Validate Scenario');
    expect(validationStatus()).toBe('Needs corrections');
    expect(fetch).toHaveBeenCalledOnce();
    const kind = document.querySelector('[data-field-path="agents.1.kind"]');
    expect(kind?.getAttribute('aria-invalid')).toBe('true');
    expect(kind?.querySelector('input:checked')).toBeNull();
    const artificial = /** @type {HTMLInputElement} */ (kind?.querySelector('input[value="artificial"]'));
    artificial.click();
    flushSync();
    expect(candidate().agents[1].kind).toBe('artificial');
    expect(draft().interpretation.generated_scenario.agents[1].kind).toBe('');
    expect(draft().interpretation.scenario_changed).toBe(true);
    expect(textOutsideJson()).toContain('The structured scenario differs from the generated draft.');
    expect(textOutsideJson()).not.toContain(diagnostics[0].message);

    const revised = 'A human curator and an artificial guide use immersive displays.';
    click('Describe with AI');
    click('Write full description');
    enter(fullDescriptionInput(), revised);
    expect(draft().source_description).toEqual({ ...sourceDescription, full_description: revised });
    expect(draft().interpretation.source_description).toEqual(sourceDescription);
    expect(draft().interpretation.source_changed).toBe(true);
    expect(textOutsideJson()).toContain('The description has changed since interpretation.');

    const savedDraft = draft();
    expect(savedDraft.interpretation.prompt_sha256).toBe(modelFindings.prompt_sha256);
    vi.stubGlobal('confirm', () => true);
    await importJson(savedDraft);
    expect(draft()).toEqual(savedDraft);
    click('Describe with AI');
    click('Write full description');
    expect(fullDescriptionInput().value).toBe(revised);
    click('Add additional notes');
    expect(notesInput().value).toBe(sourceDescription.additional_notes);
  });

  it('requires confirmation before regeneration replaces a correction', async () => {
    const confirm = vi.fn(() => false);
    const regenerated = { ...s7, use_case: { ...s7.use_case, name: 'Regenerated candidate' } };
    const fetch = vi.fn()
      .mockImplementationOnce(async () => interpretationReply(s7))
      .mockImplementationOnce(async () => interpretationReply(regenerated));
    vi.stubGlobal('fetch', fetch);
    vi.stubGlobal('confirm', confirm);
    render();
    click('Write full description');
    enter(fullDescriptionInput(), 'A virtual museum guide assists visitors.');
    click('Convert to JSON using AI');
    await until(() => expect(candidate()).toEqual(s7));
    enter(useCaseName(), 'Researcher correction');
    const corrected = draft();
    click('Describe with AI');
    click('Convert to JSON using AI');
    expect(confirm).toHaveBeenCalledOnce();
    expect(fetch).toHaveBeenCalledOnce();
    expect(draft()).toEqual(corrected);
    confirm.mockReturnValue(true);
    click('Convert to JSON using AI');
    await until(() => expect(candidate()).toEqual(regenerated));
    expect(draft().interpretation.generated_scenario).toEqual(regenerated);
  });

  it('lets a researcher remove unsupported generated entities without adding replacements', async () => {
    const task = s7.tasks[0];
    const agent = s7.agents[0];
    const generated = {
      id: s7.id, use_case: s7.use_case, goal: { ...s7.goal, required_tasks: [task.id] }, tasks: [task], agents: [agent],
    };
    const fetch = vi.fn(async () => interpretationReply(generated, { ...modelFindings, status: 'incomplete' }));
    vi.stubGlobal('fetch', fetch);
    render();
    enter(descriptionInput(), 'An unfinished scenario');
    click('Convert to JSON using AI');
    await until(() => expect(candidate()).toEqual(generated));

    for (const sectionId of ['tasks', 'agents']) {
      section(sectionId).querySelector('button')?.click();
      flushSync();
    }
    expect(candidate()).toMatchObject({ tasks: [], agents: [], goal: { required_tasks: [] } });
    expect(draft().interpretation.generated_scenario).toEqual(generated);
    click('Validate Scenario');
    expect(validationStatus()).toBe('Needs corrections');
    expect(fetch).toHaveBeenCalledOnce();
  });

  it.each(['description', 'structured scenario'])('discards an old response after editing the %s', async (field) => {
    const { fetch, respond } = pendingInterpretation();
    render();
    enter(descriptionInput(), 'Description for the model');
    click('Convert to JSON using AI');
    const requestSignal = fetch.mock.calls[0][1]?.signal;
    expect(requestSignal?.aborted).toBe(false);
    if (field === 'description') enter(descriptionInput(), 'Edited while the model was thinking');
    else {
      click('Structured Editor');
      expect(requestSignal?.aborted).toBe(false);
      enter(useCaseName(), 'My structured draft');
    }
    expect(requestSignal?.aborted).toBe(true);
    expect(textOutsideJson()).toContain('The draft changed during interpretation. Convert again to use the current draft.');
    const edited = draft();
    const response = interpretationReply(s7);
    const read = vi.spyOn(response, 'json');
    respond(response);
    await until(() => expect(read).toHaveBeenCalledOnce());
    expect(draft()).toEqual(edited);
  });

  it('preserves previous provenance when another conversion has no editable candidate', async () => {
    const findings = /** @type {typeof modelFindings} */ ({
      ...modelFindings, status: 'incomplete', diagnostics: [{ kind: 'ambiguity', message: 'The team cannot be determined.' }],
    });
    const fetch = vi.fn()
      .mockImplementationOnce(async () => interpretationReply(s7))
      .mockImplementationOnce(async () => interpretationReply(null, findings));
    vi.stubGlobal('fetch', fetch);
    vi.stubGlobal('confirm', () => true);
    render();
    enter(descriptionInput(), 'Museum guide');
    click('Convert to JSON using AI');
    await until(() => expect(candidate()).toEqual(s7));
    click('Describe with AI');
    enter(descriptionInput(), 'A different idea');
    const edited = draft();
    click('Convert to JSON using AI');
    await until(() => expect(textOutsideJson()).toContain('AI interpretation did not produce an editable scenario.'));
    expect(textOutsideJson()).not.toContain(findings.diagnostics[0].message);
    expect(draft()).toEqual(edited);
  });

  it.each([
    [502, 'interpretation_failed', 'AI interpretation failed. Try again.'],
    [503, 'interpretation_unavailable', 'AI interpretation is unavailable right now. Try again later.'],
    [422, 'invalid_request', 'Check the description length and try again.'],
  ])('shows a concise conversion failure for HTTP %i while preserving the source and hiding provider details', async (status, code, notice) => {
    const error = {
      code, message: 'Internal provider response detail', shacl_report: null,
      issues: [{ location: ['provider', 'internal-trace'], message: 'Internal provider issue detail', type: 'unexpected' }],
    };
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(error), { status })));
    render();
    const sourceText = 'A researcher describes a prototype.';
    enter(descriptionInput(), sourceText);
    click('Convert to JSON using AI');

    await until(() => expect(document.querySelector('[role="alert"]')?.textContent).toBe(notice));
    const interfaceText = textOutsideJson();
    expect(interfaceText).not.toContain(error.message);
    expect(interfaceText).not.toContain(error.issues[0].message);
    expect(interfaceText).not.toContain('internal-trace');
    expect(draft().source_description).toEqual({ use_case: sourceText });
    expect(candidate()).toBeNull();
  });
});

describe('Knowledge Explorer', () => {
  const explorer = () => document.getElementById('explorer-view');
  const reference = {
    id: 'reference:s7', scenario_id: 's7', name: 'Reference museum guide', description: 'Reference scenario detail.',
    publication_status: 'reference', graph_iri: 'urn:hi:reference:s7',
  };
  const current = { ...reference, id: 'provisional:s7', name: 'Edited museum guide', publication_status: 'provisional', graph_iri: 'urn:hi:current:s7' };
  const catalog = {
    shared_source: 'reference', scenarios: [reference],
    questions: [
      { id: 'cq1', label: 'CQ1 · Team members and roles', description: 'Which team members are recorded?', parameters: [] },
      { id: 'cq2', label: 'CQ2 · Tasks supported by capabilities', description: 'Which requirements are covered?',
        parameters: [{ id: 'capability', label: 'Supporting capability', category: 'Capability' }] },
      { id: 'cq5', label: 'CQ5 · Interactions during task execution', description: '', parameters: [] },
      { id: 'cq8', label: 'CQ8 · Experiments, metrics, and hypotheses', description: '', parameters: [] },
      { id: 'cq11', label: 'CQ11 · Contextual phenomena', description: '', parameters: [] },
    ],
  };

  it.each([false, true])('explains missing CQ5 links with source provenance when other results exist (%s)', async (hasRows) => {
    const notice = {
      code: 'interaction_execution_links_missing', source_id: reference.id,
      message: 'Interactions are recorded, but none are linked to task executions.',
    };
    const fetch = vi.fn(async (/** @type {string} */ url) => new Response(JSON.stringify(
      url.endsWith('/explorer/catalog') ? catalog : {
        sources: [reference], columns: [{ id: 'task', label: 'Task' }], truncated: false, notices: [notice],
        rows: hasRows ? [{ source_id: reference.id, values: { task: 'Explain findings' }, evidence: [] }] : [],
      },
    )));
    vi.stubGlobal('fetch', fetch);
    render();
    click('Knowledge Explorer');
    await until(() => expect(explorer()?.textContent).toContain('Experimental reference scenarios'));
    document.getElementById('explorer-source-approved')?.click();
    flushSync();
    selectValue('explorer-question', 'cq5');
    click('Run query');
    await until(() => expect(explorer()?.textContent).toContain(notice.message));
    const sourceNotice = [...(explorer()?.querySelectorAll('[role="status"]') ?? [])]
      .find((node) => node.textContent?.includes(notice.message));
    expect(sourceNotice?.textContent).toContain(reference.name);
    expect(sourceNotice?.textContent).toContain('Experimental reference');
    if (hasRows) expect(explorer()?.textContent).toContain('Explain findings');
    else {
      expect(explorer()?.textContent).toContain('No matching execution–interaction links were found.');
      expect(explorer()?.textContent).toContain('CQ5 requires recorded links between interactions and executions of goal-required tasks.');
      expect(explorer()?.querySelector('tbody')).toBeNull();
    }
  });

  it('shows an unavailable approved corpus warning alongside the reference source label', async () => {
    const warning = 'Configured approved scenario IDs have no available graphs. Showing experimental references.';
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ ...catalog, warnings: [warning] }))));
    render();
    click('Knowledge Explorer');
    await until(() => expect(explorer()?.textContent).toContain(warning));
    expect(explorer()?.textContent).toContain('Experimental reference scenarios');
  });

  it('opens concept search and draft comparison from the Explorer while preserving Builder edits', async () => {
    const shared = { ...reference, id: 'reference:s5', scenario_id: 's5', name: 'Recorded S5 diagnosis' };
    const fetch = vi.fn(async (/** @type {string} */ url, /** @type {RequestInit} */ _request) => new Response(JSON.stringify(
      url.endsWith('/explorer/catalog') ? { ...catalog, scenarios: [shared] } : {
        sources: [shared], columns: [{ id: 'concept', label: 'HINT concept' }, { id: 'overlap', label: 'Vocabulary overlap' }],
        rows: [{ source_id: shared.id, values: { concept: 'Diagnosis Accuracy Metric', overlap: 'Recorded in both' },
          evidence: [{ label: 'Metric', iri: 'https://w3id.org/hi-thesaurus/DiagnosisAccuracyMetric' }] }],
        truncated: false,
      },
    )));
    vi.stubGlobal('fetch', fetch);
    render();
    await importJson(s5);
    enter(useCaseName(), 'My diagnosis comparison draft');
    const edited = draft();
    click('Knowledge Explorer');
    await until(() => expect(explorer()?.textContent).toContain(shared.name));
    click('Find concepts');
    selectValue('concept-value', 'KnowledgeGraphQueryingCapability');
    document.getElementById('concept-run')?.click();
    flushSync();
    await until(() => expect(explorer()?.textContent).toContain('1 recorded concept relationships.'));
    expect(JSON.parse(String(fetch.mock.calls.at(-1)?.[1].body))).toEqual({
      scope: 'shared', compare: false, category: 'Capability', concept: 'KnowledgeGraphQueryingCapability',
    });

    click('Compare scenarios');
    selectValue('concept-scenario', 's5');
    document.getElementById('concept-run')?.click();
    flushSync();
    await until(() => expect(document.getElementById('concept-results-heading')).not.toBeNull());
    await until(() => expect(fetch).toHaveBeenCalledTimes(3));
    expect(JSON.parse(String(fetch.mock.calls.at(-1)?.[1].body))).toEqual({
      scope: 'combined', compare: true, category: null, scenario: edited.scenario, shared_scenario_id: 's5',
    });
    click('Competency questions');
    expect(document.getElementById('explorer-question')?.closest('[hidden]')).toBeNull();
    click('Scenario Builder');
    expect(useCaseName().value).toBe('My diagnosis comparison draft');
    expect(draft()).toEqual(edited);
  });

  it('combines explicitly selected sources, renders row evidence, and preserves Builder edits', async () => {
    const fetch = vi.fn(async (/** @type {string} */ url, /** @type {RequestInit} */ request) => {
      if (url.endsWith('/explorer/catalog')) return new Response(JSON.stringify(catalog));
      const payload = JSON.parse(String(request.body));
      return new Response(JSON.stringify(payload.question_id === 'cq11' ? {
        sources: [reference], columns: [{ id: 'context', label: 'Context' }], rows: [], truncated: false,
      } : {
        sources: [current, reference], columns: [{ id: 'task', label: 'Task' }, { id: 'method', label: 'Method' }], truncated: true,
        rows: [{ source_id: current.id, values: { task: 'Inspect museum exhibits', method: null }, evidence: [{ label: 'Task', iri: 'urn:hi:task:own' }] },
          { source_id: reference.id, values: { task: 'Guide museum visitors', method: 'Observation' }, evidence: [{ label: 'Task', iri: 'urn:hi:task:shared' }] }],
      }));
    });
    vi.stubGlobal('fetch', fetch);
    render();
    await importJson(s7);
    enter(useCaseName(), current.name);
    const edited = draft();
    expect(fetch).not.toHaveBeenCalled();

    click('Knowledge Explorer');
    expect(document.getElementById('builder-view')?.hidden).toBe(true);
    expect(explorer()?.hidden).toBe(false);
    await until(() => expect(explorer()?.textContent).toContain('Experimental reference scenarios'));
    document.getElementById('explorer-source-combined')?.click();
    flushSync();
    selectValue('explorer-scenario', reference.scenario_id);
    expect(explorer()?.textContent).toContain(reference.description);
    selectValue('explorer-question', 'cq2');
    selectValue('explorer-parameter-capability', 'SensingCapability');
    click('Run query');
    await until(() => expect(explorer()?.textContent).toContain('Inspect museum exhibits'));
    expect(fetch).toHaveBeenLastCalledWith(expect.stringContaining('/explorer/query'), expect.objectContaining({
      method: 'POST', body: expect.any(String),
    }));
    expect(JSON.parse(String(fetch.mock.calls.at(-1)?.[1].body))).toEqual({
      question_id: 'cq2', scope: 'combined', scenario: edited.scenario, shared_scenario_id: 's7', parameters: { capability: 'SensingCapability' },
    });
    const rows = explorer()?.querySelectorAll('tbody tr');
    expect(rows).toHaveLength(2);
    expect(rows?.[0].textContent).toContain('Provisional draft');
    expect(rows?.[0].textContent).toContain('Not recorded');
    expect(rows?.[1].textContent).toContain('Experimental reference');
    rows?.[0]?.querySelector('summary')?.click();
    expect(rows?.[0]?.querySelector('details')?.open).toBe(true);
    expect(rows?.[0]?.querySelector('code')?.textContent).toBe('urn:hi:task:own');
    expect(explorer()?.textContent).toContain('The result limit was reached.');

    document.getElementById('explorer-source-approved')?.click();
    flushSync();
    selectValue('explorer-question', 'cq11');
    expect(explorer()?.textContent).not.toContain('Inspect museum exhibits');
    click('Run query');
    await until(() => expect(explorer()?.textContent).toContain('No evidence was found'));
    expect(JSON.parse(String(fetch.mock.calls.at(-1)?.[1].body))).toEqual({ question_id: 'cq11', scope: 'shared', shared_scenario_id: 's7' });

    click('Scenario Builder');
    expect(explorer()?.hidden).toBe(true);
    expect(useCaseName().value).toBe(current.name);
    expect(draft()).toEqual(edited);
    expect(validationStatus()).toBe('Not validated');
  });

  it('keeps draft queries usable when the shared catalog fails and discards results after a draft edit', async () => {
    /** @type {(response: Response) => void} */
    let respond = () => {};
    const fetch = vi.fn(async (/** @type {string} */ url, /** @type {RequestInit} */ _request) => {
      if (url.endsWith('/explorer/catalog')) return new Response('{}', { status: 503 });
      return new Promise((resolve) => { respond = resolve; });
    });
    vi.stubGlobal('fetch', fetch);
    render();
    await importJson(s7);
    click('Knowledge Explorer');
    await until(() => expect(explorer()?.textContent).toContain('Shared scenarios could not be loaded.'));
    expect(explorer()?.querySelectorAll('#explorer-question option')).toHaveLength(5);
    click('Run query');
    expect(explorer()?.textContent).toContain('Running query…');
    expect(JSON.parse(String(fetch.mock.calls.at(-1)?.[1].body))).toEqual({ question_id: 'cq1', scope: 'draft', scenario: s7 });

    click('Scenario Builder');
    enter(useCaseName(), 'New museum draft');
    expect(fetch.mock.calls.at(-1)?.[1].signal?.aborted).toBe(true);
    click('Knowledge Explorer');
    expect(explorer()?.textContent).not.toContain('Running query…');
    const lateResponse = new Response(JSON.stringify({
      sources: [current], columns: [{ id: 'task', label: 'Task' }], truncated: false,
      rows: [{ source_id: current.id, values: { task: 'Stale evidence result' }, evidence: [] }],
    }));
    const read = vi.spyOn(lateResponse, 'json');
    respond(lateResponse);
    await until(() => expect(read).toHaveBeenCalled());
    expect(explorer()?.textContent).not.toContain('Stale evidence result');
    expect(fetch.mock.calls.filter(([url]) => url.endsWith('/explorer/catalog'))).toHaveLength(1);
  });

  it('labels approved scenarios and lets a researcher query them without a Builder draft', async () => {
    const approved = { ...reference, id: 'approved:s7', name: 'Approved museum guide', publication_status: 'approved' };
    const fetch = vi.fn(async (/** @type {string} */ url, /** @type {RequestInit} */ _request) => new Response(JSON.stringify(
      url.endsWith('/explorer/catalog') ? { ...catalog, shared_source: 'approved', scenarios: [approved] }
        : { sources: [approved], columns: [], rows: [], truncated: false },
    )));
    vi.stubGlobal('fetch', fetch);
    render();
    click('Knowledge Explorer');
    await until(() => expect(explorer()?.textContent).toContain('Approved scenarios'));
    expect(explorer()?.textContent).not.toContain('Experimental reference');
    const run = /** @type {HTMLButtonElement} */ (document.getElementById('explorer-run'));
    expect(run.disabled).toBe(true);
    document.getElementById('explorer-source-approved')?.click();
    flushSync();
    selectValue('explorer-scenario', approved.scenario_id);
    expect(explorer()?.querySelector('#explorer-scenario option:checked')?.textContent).toContain('Approved museum guide');
    expect(run.disabled).toBe(false);
    click('Run query');
    await until(() => expect(explorer()?.textContent).toContain('No evidence was found'));
    expect(JSON.parse(String(fetch.mock.calls.at(-1)?.[1].body))).toEqual({ question_id: 'cq1', scope: 'shared', shared_scenario_id: 's7' });
  });
});
