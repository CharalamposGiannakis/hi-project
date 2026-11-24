// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';
import KnowledgeExplorer from './KnowledgeExplorer.svelte';
import s1 from '../../../examples/s1.json';

/** @type {Record<string, string>} */
const pendingQuestions = {
  cq3: 'What candidate team compositions satisfy all capability requirements for achieving a specific goal?',
  cq4: 'How can we infer team eligibility, task assignment, or contextual influences?',
  cq12: "Under what conditions does an agent's behaviour comply with or violate a contextual constraint associated with a use case?",
};
const questions = Array.from({ length: 12 }, (_, index) => {
  const id = `cq${index + 1}`;
  return {
    id, label: `CQ${index + 1}`, question: pendingQuestions[id] ?? `Original question ${index + 1}`,
    description: '', parameters: [],
    status: Object.hasOwn(pendingQuestions, id) ? 'scientific_review_pending' : 'available',
    pending_reason: Object.hasOwn(pendingQuestions, id) ? 'Scientific clarification is needed.' : null,
  };
});
const source = { id: 'reference:s5', scenario_id: 's5', name: 'S5', description: null, publication_status: 'reference', graph_iri: 'urn:reference:s5' };
const catalog = { shared_source: 'reference', scenarios: [source], questions };
/** @type {ReturnType<typeof mount> | undefined} */
let component;
afterEach(async () => {
  if (component) await unmount(component);
  component = undefined;
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
});
/** @param {Partial<import('svelte').ComponentProps<typeof KnowledgeExplorer>>} [overrides] */
function render(overrides = {}) {
  const props = $state({ active: true, uploads: /** @type {import('./api.js').SessionUpload[]} */ ([]), focusSourceId: '', ...overrides });
  component = mount(KnowledgeExplorer, { target: document.body, props });
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
/** @param {() => void} assertion */
async function until(assertion) { await vi.waitFor(() => { flushSync(); assertion(); }); }

it('shows all twelve original-numbered questions and blocks pending questions before sending a request', async () => {
  const fetch = vi.fn(async () => new Response(JSON.stringify(catalog)));
  vi.stubGlobal('fetch', fetch);
  render();
  await until(() => expect(document.body.textContent).toContain('Experimental reference scenarios'));
  expect(document.querySelectorAll('#explorer-question option')).toHaveLength(12);
  expect([...document.querySelectorAll('#explorer-question option')].map((option) => option.getAttribute('value')))
    .toEqual(Array.from({ length: 12 }, (_, index) => `cq${index + 1}`));
  for (const [id, question] of Object.entries(pendingQuestions)) {
    select('explorer-question', id);
    expect(document.body.textContent).toContain(question);
    expect(document.body.textContent).toContain('Scientific review pending');
    expect(document.body.textContent).toContain('Scientific clarification is needed.');
    expect(/** @type {HTMLButtonElement} */ (document.getElementById('explorer-run')).disabled).toBe(true);
    document.querySelector('form')?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    flushSync();
  }
  expect(fetch).toHaveBeenCalledTimes(1);
});

it('requires selected session scenarios for local queries while shared knowledge stays available', async () => {
  const fetch = vi.fn(async (/** @type {string} */ url, /** @type {RequestInit} */ _options) => new Response(JSON.stringify(
    url.endsWith('/explorer/catalog') ? catalog : { sources: [], columns: [], rows: [], truncated: false },
  )));
  vi.stubGlobal('fetch', fetch);
  render();
  await until(() => expect(document.body.textContent).toContain('Experimental reference scenarios'));
  expect(/** @type {HTMLButtonElement} */ (document.getElementById('explorer-run')).disabled).toBe(true);
  expect(document.body.textContent).toContain('Add a validated scenario from the Builder');
  document.getElementById('explorer-source-approved')?.click();
  flushSync();
  document.getElementById('explorer-run')?.click();
  await until(() => expect(fetch.mock.calls.some(([url]) => url.endsWith('/explorer/query'))).toBe(true));
  expect(JSON.parse(String(fetch.mock.calls.at(-1)?.[1]?.body))).toEqual({ question_id: 'cq1', scope: 'shared' });
});

it('focuses a newly added Builder snapshot without auto-querying or resetting ordinary navigation', async () => {
  const fetch = vi.fn(async () => new Response(JSON.stringify(catalog)));
  vi.stubGlobal('fetch', fetch);
  const props = render({ uploads: [{ id: 'builder-one', file_name: 'Builder · S1', scenario: s1, selected: true }] });
  await until(() => expect(document.body.textContent).toContain('Experimental reference scenarios'));
  document.getElementById('explorer-source-approved')?.click();
  const compare = [...document.querySelectorAll('button')].find((button) => button.textContent === 'Compare scenarios');
  compare?.click();
  flushSync();
  expect(compare?.getAttribute('aria-pressed')).toBe('true');
  props.active = false;
  flushSync();
  props.focusSourceId = 'builder-one';
  props.active = true;
  flushSync();
  expect(compare?.getAttribute('aria-pressed')).toBe('false');
  expect(/** @type {HTMLInputElement} */ (document.getElementById('explorer-source-session')).checked).toBe(true);
  expect(fetch).toHaveBeenCalledTimes(1);
  document.getElementById('explorer-source-approved')?.click();
  props.active = false;
  flushSync();
  props.active = true;
  flushSync();
  expect(/** @type {HTMLInputElement} */ (document.getElementById('explorer-source-approved')).checked).toBe(true);
});

it('queries selected session scenarios with shared knowledge and excludes unchecked scenarios', async () => {
  const fetch = vi.fn(async (/** @type {string} */ url, /** @type {RequestInit} */ _options) => new Response(JSON.stringify(
    url.endsWith('/explorer/catalog') ? catalog
      : url.endsWith('/scenarios/preview') ? { rdf: '', triple_count: 1, validation: { conforms: true, report: 'Conforms' } }
      : { sources: [], columns: [], rows: [], truncated: false },
  )));
  vi.stubGlobal('fetch', fetch);
  render();
  await until(() => expect(document.querySelectorAll('#explorer-question option')).toHaveLength(12));
  const input = /** @type {HTMLInputElement} */ (document.getElementById('explorer-upload-files'));
  Object.defineProperty(input, 'files', { value: [
    { name: 'first.json', text: async () => JSON.stringify(s1) },
    { name: 'second.json', text: async () => JSON.stringify(s1) },
  ], configurable: true });
  input.dispatchEvent(new Event('change', { bubbles: true }));
  await until(() => expect(document.querySelectorAll('input[aria-label^="Include "]')).toHaveLength(2));
  document.getElementById('explorer-source-combined')?.click();
  flushSync();
  document.getElementById('explorer-run')?.click();
  await until(() => expect(fetch.mock.calls.some(([url]) => url.endsWith('/explorer/query'))).toBe(true));
  const sent = JSON.parse(String(fetch.mock.calls.find(([url]) => url.endsWith('/explorer/query'))?.[1]?.body));
  expect(sent).not.toHaveProperty('scenario');
  expect(sent.scope).toBe('combined');
  expect(sent.uploads).toHaveLength(2);
  expect(sent.uploads[0].id).not.toBe(sent.uploads[1].id);
  expect(sent.uploads.map((/** @type {import('./api.js').UploadedScenario} */ entry) => /** @type {Record<string, unknown>} */ (entry.scenario).id)).toEqual(['s1', 's1']);
  document.querySelector('input[aria-label="Include first.json"]')?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  flushSync();
  document.getElementById('explorer-run')?.click();
  await until(() => expect(fetch.mock.calls.filter(([url]) => url.endsWith('/explorer/query'))).toHaveLength(2));
  const latest = JSON.parse(String(fetch.mock.calls.at(-1)?.[1]?.body));
  expect(latest.uploads).toHaveLength(1);
  expect(latest.uploads[0].file_name).toBe('second.json');
  expect(document.getElementById('explorer-include-current')).toBeNull();
  expect(document.body.textContent).not.toContain('Include current Builder scenario');
});
