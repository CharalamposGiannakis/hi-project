// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';
import App from './App.svelte';
import s5 from '../../examples/s5.json';
import s7 from '../../examples/s7.json';

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
    await until(() => expect(document.activeElement).toBe(section('experiments').querySelector('summary')));
    expect(section('experiments').open).toBe(true);

    click('Expand all');
    const agent = document.getElementById(`agent-${s7.agents[0].id}`)?.closest('.item');
    click('Collapse all');
    section('agents').querySelector('summary')?.click();
    await until(() => expect(section('agents').open).toBe(true));
    // Removing a referenced member leaves explicit execution/interaction repair errors.
    agent?.querySelector('button')?.click();
    flushSync();
    expect(section('executions').open).toBe(true);
    expect(section('interactions').open).toBe(true);
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
  it('expands a single read-only viewer, preserves JSON through Copy/Download, and restores the layout', async () => {
    const clipboard = vi.fn(async (/** @type {string} */ value) => { void value; });
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: clipboard } });
    const createObjectURL = vi.fn(() => 'blob:test-json');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', class extends URL { static createObjectURL = createObjectURL; static revokeObjectURL = revokeObjectURL; });
    const download = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    render();
    await importJson(s7);
    const pre = jsonNode();
    click('Expand JSON');
    expect(document.querySelector('main')?.classList.contains('json-expanded')).toBe(true);
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
    click('Restore JSON size');
    expect(document.querySelector('main')?.classList.contains('json-expanded')).toBe(false);
    expect(jsonNode()).toBe(pre);
    expect(draft()).toEqual(s7);
    Reflect.deleteProperty(navigator, 'clipboard');
  });

  it('preserves preview and save outcomes across navigation and JSON expansion, invalidating them only on data edits', async () => {
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
    click('Expand JSON');
    click('Restore JSON size');
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
