// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';
import CrossScenarioExplorer from './CrossScenarioExplorer.svelte';
import { fromContract, toContract } from './scenario.js';
import s5 from '../../../examples/s5.json';

const draft = toContract(fromContract(s5));
const reference = {
  id: 'reference:s5', scenario_id: 's5', name: 'Shared medical diagnosis', description: 'A recorded comparison scenario.',
  publication_status: 'reference', graph_iri: 'urn:reference:s5',
};
const own = { ...reference, id: 'provisional:s5', name: 'My medical diagnosis', publication_status: 'provisional', graph_iri: 'urn:private:draft' };
const catalog = { shared_source: 'reference', scenarios: [reference], questions: [], warnings: ['Verify approval of the configured corpus.'] };
const columns = [
  { id: 'concept', label: 'HINT concept' }, { id: 'connection', label: 'Recorded relationship' },
  { id: 'related', label: 'Related entity' }, { id: 'overlap', label: 'Vocabulary overlap' },
];
const rows = [
  { source_id: own.id, values: { concept: 'Knowledge Graph Querying Capability', connection: 'Agent capability', related: 'My AI', overlap: 'Recorded in both' },
    evidence: [{ label: 'Concept', iri: 'https://w3id.org/hi-thesaurus/KnowledgeGraphQueryingCapability' }] },
  { source_id: reference.id, values: { concept: 'Knowledge Graph Querying Capability', connection: 'Task requirement', related: 'Prepare diagnosis', overlap: 'Recorded in both' },
    evidence: [{ label: 'Task', iri: 'urn:reference:s5:task' }] },
  { source_id: reference.id, values: { concept: 'Privacy Constraint', connection: 'Context constraint', related: null, overlap: 'Recorded only in shared' },
    evidence: [{ label: 'Context', iri: 'urn:reference:s5:context' }] },
];

/** @type {ReturnType<typeof mount> | undefined} */
let component;
afterEach(async () => {
  if (component) await unmount(component);
  component = undefined;
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
});

/** @param {Partial<import('svelte').ComponentProps<typeof CrossScenarioExplorer>>} [overrides] */
function render(overrides = {}) {
  const props = $state({
    active: true, compare: false, draft, shared: /** @type {import('./api.js').ExplorerCatalog} */ (catalog),
    loading: false, catalogFailed: false, onretry: async () => {}, ...overrides,
  });
  component = mount(CrossScenarioExplorer, { target: document.body, props });
  flushSync();
  return props;
}

/** @param {string} id @param {string} value */
function select(id, value) {
  const input = /** @type {HTMLSelectElement} */ (document.getElementById(id));
  input.value = value;
  input.dispatchEvent(new Event('change', { bubbles: true }));
  flushSync();
}
function run() {
  document.getElementById('concept-run')?.click();
  flushSync();
}
const button = () => /** @type {HTMLButtonElement} */ (document.getElementById('concept-run'));
/** @param {() => void} assertion */
async function until(assertion) {
  await vi.waitFor(() => { flushSync(); assertion(); });
}
/** @param {unknown} answer */
const reply = (answer) => vi.fn(async (/** @type {string} */ _url, /** @type {RequestInit} */ _request) => new Response(JSON.stringify(answer)));

describe('cross-scenario concept exploration', () => {
  it('finds a selected capability and displays the scenario relationship and RDF evidence', async () => {
    const fetch = reply({ sources: [reference], columns, rows: [rows[1]], truncated: false });
    vi.stubGlobal('fetch', fetch);
    render();
    select('concept-value', 'KnowledgeGraphQueryingCapability');
    run();
    await until(() => expect(document.querySelector('tbody')?.textContent).toContain('Prepare diagnosis'));
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/explorer/concepts'), expect.objectContaining({
      method: 'POST', body: JSON.stringify({ scope: 'shared', compare: false, category: 'Capability', concept: 'KnowledgeGraphQueryingCapability' }),
    }));
    expect(document.body.textContent).toContain('Experimental reference');
    const details = /** @type {HTMLDetailsElement} */ (document.querySelector('tbody details'));
    details.querySelector('summary')?.click();
    expect(details.open).toBe(true);
    expect(details.textContent).toContain('urn:reference:s5:task');
    expect(document.body.textContent).toContain(catalog.warnings[0]);
  });

  it('resets a previous concept when changing category and shows recorded privacy relationships', async () => {
    const fetch = reply({ sources: [reference], columns, rows: [rows[2]], truncated: false });
    vi.stubGlobal('fetch', fetch);
    render();
    select('concept-value', 'KnowledgeGraphQueryingCapability');
    select('concept-category', 'Constraint');
    expect(/** @type {HTMLSelectElement} */ (document.getElementById('concept-value')).value).toBe('');
    select('concept-value', 'PrivacyConstraint');
    run();
    await until(() => expect(document.querySelector('tbody')?.textContent).toContain('Context constraint'));
    expect(JSON.parse(String(fetch.mock.calls.at(-1)?.[1]?.body))).toEqual({
      scope: 'shared', compare: false, category: 'Constraint', concept: 'PrivacyConstraint',
    });
    expect(document.body.textContent).toContain('Not recorded');
  });

  it('requires an explicit shared scenario for comparison and keeps matching IDs distinguishable', async () => {
    const fetch = reply({ sources: [own, reference], columns, rows, truncated: true });
    vi.stubGlobal('fetch', fetch);
    render({ compare: true });
    expect(button().disabled).toBe(true);
    select('concept-scenario', 's5');
    run();
    await until(() => expect(document.querySelectorAll('tbody tr')).toHaveLength(3));
    expect(JSON.parse(String(fetch.mock.calls.at(-1)?.[1]?.body))).toEqual({
      scope: 'combined', compare: true, category: null, scenario: draft, shared_scenario_id: 's5',
    });
    const renderedRows = [...document.querySelectorAll('tbody tr')];
    expect(renderedRows[0].textContent).toContain('My medical diagnosis');
    expect(renderedRows[0].textContent).toContain('Provisional draft');
    expect(renderedRows[1].textContent).toContain('Shared medical diagnosis');
    expect(renderedRows[1].textContent).toContain('Experimental reference');
    expect(renderedRows[0].textContent).toContain('Recorded in both');
    expect(renderedRows[2].textContent).toContain('Recorded only in shared');
    expect(document.body.textContent).toContain('recorded vocabulary overlap');
    expect(document.body.textContent).toContain('The result limit was reached');
  });

  it('cancels a pending comparison when its draft changes and discards the late result', async () => {
    /** @type {(response: Response) => void} */
    let respond = () => {};
    const fetch = vi.fn((_url, _request) => new Promise((resolve) => { respond = resolve; }));
    vi.stubGlobal('fetch', fetch);
    const props = render({ compare: true });
    select('concept-scenario', 's5');
    run();
    expect(document.body.textContent).toContain('Comparing scenarios…');
    props.draft = { ...draft, use_case: { ...draft.use_case, name: 'Changed draft' } };
    flushSync();
    expect(fetch.mock.calls[0][1].signal.aborted).toBe(true);
    respond(new Response(JSON.stringify({ sources: [own, reference], columns, rows, truncated: false })));
    await until(() => expect(document.body.textContent).not.toContain('Comparing scenarios…'));
    expect(document.querySelector('tbody')).toBeNull();
  });

  it('allows a draft search after a catalog failure and explains a validation rejection', async () => {
    const fetch = vi.fn(async (/** @type {string} */ _url, /** @type {RequestInit} */ _request) => new Response(JSON.stringify({
      code: 'invalid_request', message: 'The current scenario is incomplete.', issues: [], shacl_report: null,
    }), { status: 422 }));
    vi.stubGlobal('fetch', fetch);
    render({ shared: null, catalogFailed: true });
    expect(button().disabled).toBe(true);
    expect(document.body.textContent).toContain('Shared scenarios could not be loaded');
    select('concept-scope', 'draft');
    run();
    await until(() => expect(document.body.textContent).toContain('The current scenario is incomplete.'));
    expect(document.body.textContent).toContain('Use technical validation');
    expect(JSON.parse(String(fetch.mock.calls.at(-1)?.[1]?.body))).toEqual({
      scope: 'draft', compare: false, category: 'Capability', scenario: draft,
    });
  });

  it('requires a Builder draft for comparison', () => {
    render({ compare: true, draft: null });
    select('concept-scenario', 's5');
    expect(button().disabled).toBe(true);
    expect(document.body.textContent).toContain('Start or open a structured scenario');
  });
});
