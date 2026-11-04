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
    expect(draft()).toEqual(canonical);
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
    expect(draft()).toEqual(expected);
    expect(document.querySelectorAll('input:checked').length).toBeGreaterThan(10);
  });

  it.each(['Show in form', 'Validate & preview RDF', 'Save to GraphDB', 'Download JSON'])('%s reveals all sections containing local validation errors on every request', (action) => {
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    render();
    click('Collapse all');
    click(action);
    expect(sections().filter((element) => element.open).map((element) => element.id)).toEqual([
      'section-use_case', 'section-goal', 'section-tasks', 'section-agents',
    ]);
    expect(section('agents').querySelector('.error-count')?.textContent).toContain('issues');
    click('Collapse all');
    click(action);
    expect(section('agents').open).toBe(true);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('keeps erroneous sections manually collapsed across native toggle events, unrelated edits, and error resolution', async () => {
    render();
    click('Show in form');
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
    click('Show in form');
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
    click('Validate & preview RDF');
    for (const id of ['capabilities', 'executions', 'experiments', 'evaluations', 'interactions']) {
      expect(section(id).open).toBe(true);
      expect(section(id).querySelector('.error-count')).not.toBeNull();
    }
    click('Collapse all');
    const link = [...document.querySelectorAll('.issues button')].find((button) => button.textContent?.includes('experiments.1.null_hypothesis'));
    if (!(link instanceof HTMLButtonElement)) throw new Error('Missing nested issue link');
    link.click();
    const experimentId = draft().experiments[1].id;
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
    expect(draft().agents).toHaveLength(2);
    expect(draft().agents.some((/** @type {{id: string}} */ agent) => agent.id === removedId)).toBe(false);
    expect(document.getElementById(`agent-${removedId}`)).toBeNull();
    expect(draft().executions[0].agent).toBe(removedId);
    expect(draft().interactions[0].agents).toContain(removedId);
    expect(section('executions').open).toBe(true);
    expect(section('interactions').open).toBe(true);
    expect(section('executions').textContent).toContain(`Agent "${removedId}" no longer exists`);
    expect(section('interactions').textContent).toContain(`Unknown agent ID: ${removedId}`);
    expect(document.querySelector('.issues')?.textContent).toContain('executions.0.agent');
    expect(document.querySelector('.issues')?.textContent).toContain('interactions.0.agents');
  });

  it.each(['Validate & preview RDF', 'Save to GraphDB'])('%s opens sections for backend validation locations and clears stale feedback after editing', async (action) => {
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
    click(action);
    await until(() => expect(section('experiments').open).toBe(true));
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
    click('Validate & preview RDF');
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
    expect(draft()).toEqual(s7);
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
    click('Validate & preview RDF');
    enter(/** @type {HTMLInputElement} */ (document.getElementById('use-case-name')), 'Updated museum guide');
    respond(new Response(JSON.stringify({
      code: 'invalid_request', message: 'Old validation result.', shacl_report: null,
      issues: [{ location: ['body', 'experiments', 0, 'null_hypothesis'], message: 'Old hypothesis error.', type: 'value_error' }],
    }), { status: 422 }));
    await until(() => expect(document.body.textContent).toContain('changed since the last preview'));
    expect(section('experiments').open).toBe(false);
    expect(document.querySelector('.issues')).toBeNull();
  });
});

describe('Scenario JSON and submission workflows', () => {
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
    expect(JSON.parse(snapshot)).toEqual(s7);
    enter(/** @type {HTMLInputElement} */ (document.getElementById('use-case-name')), 'Unsaved museum edits');
    expect(JSON.parse(snapshot)).toEqual(s7);
    const latest = JSON.parse(await requestScenarioJson(url.hash.slice(1)));
    expect(latest).toEqual({ ...s7, use_case: { ...s7.use_case, name: 'Unsaved museum edits' } });
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
    expect([...document.querySelectorAll('button')].map((button) => button.textContent?.trim())).toEqual(expect.arrayContaining(['Copy', 'Download JSON', 'Validate & preview RDF', 'Save to GraphDB']));
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
    expect(JSON.parse(clipboard.mock.calls[0][0])).toEqual(s7);
    click('Download JSON');
    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(download).toHaveBeenCalledOnce();
    expect(/** @type {HTMLAnchorElement} */ (download.mock.contexts[0]).download).toBe('scenario-s7.json');
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:test-json');
    expect(document.body.textContent).toContain('JSON downloaded to your computer.');
    expect(jsonNode()).toBe(pre);
    expect(draft()).toEqual(s7);
    Reflect.deleteProperty(navigator, 'clipboard');
  });

  it('preserves preview and save outcomes while inspecting JSON, invalidating them only on data edits', async () => {
    const validation = { conforms: true, report: 'Conforms: True' };
    const fetch = vi.fn(async (/** @type {string} */ url) => new Response(JSON.stringify(url.endsWith('/preview') ? {
      scenario_id: 's7', rdf_format: 'nt', rdf: '<urn:s7> <urn:p> "test" .', triple_count: 173, validation,
    } : {
      scenario_id: 's7', repository_id: 'hi', graph_iri: 'urn:hi-app:graph:scenario:s7',
      workbench_url: 'http://localhost:7200', workbench_graph_url: 'http://localhost:7200/graph',
      use_case_iri: 'urn:use-case', team_iri: 'urn:team', triple_count: 173, validation,
    }), { status: url.endsWith('/preview') ? 200 : 201 }));
    vi.stubGlobal('fetch', fetch);
    render();
    await importJson(s7);
    click('Validate & preview RDF');
    await until(() => expect(document.querySelector('pre.rdf')).not.toBeNull());
    click('Save to GraphDB');
    await until(() => expect(document.body.textContent).toContain('Saved in GraphDB'));
    click('Expand all');
    click('Collapse all');
    expect(document.querySelector('.json-panel a')?.getAttribute('target')).toBe('_blank');
    expect(document.body.textContent).toContain('173 triples · not saved');
    expect(document.body.textContent).toContain('Saved in GraphDB');
    expect(fetch).toHaveBeenCalledTimes(2);
    for (const call of fetch.mock.calls) expect(JSON.parse(/** @type {any} */ (call)[1].body)).toEqual(s7);
    enter(/** @type {HTMLInputElement} */ (document.getElementById('use-case-name')), 'Edited museum scenario');
    expect(document.querySelector('pre.rdf')).toBeNull();
    expect(document.body.textContent).not.toContain('Saved in GraphDB');
    expect(document.body.textContent).toContain('The form has changed since scenario');
  });
});
