// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';
import ScenarioUploads from './ScenarioUploads.svelte';
import s1 from '../../../examples/s1.json';

/** @type {ReturnType<typeof mount> | undefined} */
let component;
afterEach(async () => {
  if (component) await unmount(component);
  component = undefined;
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
});

function render() {
  const state = $state({ uploads: /** @type {import('./api.js').SessionUpload[]} */ ([]) });
  component = mount(ScenarioUploads, { target: document.body, props: {
    get uploads() { return state.uploads; }, set uploads(value) { state.uploads = value; },
  } });
  flushSync();
  return state;
}
/** @param {{name:string,text:()=>Promise<string>}[]} files */
function upload(files) {
  const input = /** @type {HTMLInputElement} */ (document.getElementById('explorer-upload-files'));
  Object.defineProperty(input, 'files', { value: files, configurable: true });
  input.dispatchEvent(new Event('change', { bubbles: true }));
  flushSync();
}
/** @param {string} name @param {unknown} data */
const file = (name, data) => ({ name, text: async () => JSON.stringify(data) });
const valid = () => new Response(JSON.stringify({ rdf: '<urn:s> <urn:p> <urn:o> .', triple_count: 1, validation: { conforms: true, report: 'Conforms' } }));
/** @param {() => void} assertion */
async function until(assertion) { await vi.waitFor(() => { flushSync(); assertion(); }); }

it('validates multiple files and keeps duplicate scenario IDs as separate selectable uploads', async () => {
  const fetch = vi.fn(async (/** @type {string} */ _url, /** @type {RequestInit} */ _options) => valid());
  vi.stubGlobal('fetch', fetch);
  const state = render();
  upload([file('first.json', s1), file('second.json', s1)]);
  await until(() => expect(state.uploads).toHaveLength(2));
  expect(state.uploads[0].id).not.toBe(state.uploads[1].id);
  expect(state.uploads.every((entry) => entry.selected)).toBe(true);
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(fetch).toHaveBeenLastCalledWith(expect.stringContaining('/scenarios/preview'), expect.objectContaining({ body: JSON.stringify(s1) }));
  expect(document.body.textContent).toContain(s1.use_case.name);
  expect(document.body.textContent).toContain('(s1)');
  const checkbox = /** @type {HTMLInputElement} */ (document.querySelector('input[type="checkbox"]'));
  checkbox.click();
  flushSync();
  expect(state.uploads[0].selected).toBe(false);
  document.querySelector('button[aria-label="Remove second.json"]')?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  flushSync();
  expect(state.uploads).toHaveLength(1);
});

it('extracts the canonical candidate from a Pillar 1 draft without sending descriptions', async () => {
  const fetch = vi.fn(async (/** @type {string} */ _url, /** @type {RequestInit} */ _options) => valid());
  vi.stubGlobal('fetch', fetch);
  const state = render();
  upload([file('draft.json', {
    source_description: { use_case: 'Original researcher description' }, scenario: s1,
    interpretation: { status: 'not_interpreted', diagnostics: [] },
  })]);
  await until(() => expect(state.uploads).toHaveLength(1));
  expect(fetch.mock.calls[0][1].body).toBe(JSON.stringify(s1));
  expect(state.uploads[0].scenario).toEqual(s1);
});

it('reports per-file JSON and canonical validation errors while preserving valid files', async () => {
  const fetch = vi.fn(async (/** @type {string} */ _url, /** @type {RequestInit} */ options) => JSON.parse(String(options.body)).id === 'invalid'
    ? new Response(JSON.stringify({
      code: 'invalid_request', message: 'Scenario JSON failed structural validation.',
      issues: [{ location: ['body', 'agents', 0, 'name'], message: 'Field required', type: 'missing' }],
      shacl_report: null,
    }), { status: 422 }) : valid());
  vi.stubGlobal('fetch', fetch);
  const state = render();
  upload([{ name: 'broken.json', text: async () => '{' }, file('invalid.json', { id: 'invalid' }), file('valid.json', s1)]);
  await until(() => expect(state.uploads).toHaveLength(1));
  expect(document.body.textContent).toContain('broken.json');
  expect(document.body.textContent).toContain('not valid JSON');
  expect(document.body.textContent).toContain('invalid.json');
  expect(document.body.textContent).toContain('agents.0.name');
  expect(document.body.textContent).toContain('Field required');
});

it('shows SHACL details and keeps an invalid candidate out of the selectable sources', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
    code: 'shacl_failed', message: 'Generated RDF failed SHACL validation.', issues: [], shacl_report: 'Constraint violation report',
  }), { status: 422 })));
  const state = render();
  upload([file('invalid-rdf.json', s1)]);
  await until(() => expect(document.body.textContent).toContain('Constraint violation report'));
  expect(state.uploads).toHaveLength(0);
});
