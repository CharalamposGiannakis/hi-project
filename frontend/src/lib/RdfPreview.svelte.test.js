// @vitest-environment jsdom
// A `.svelte.test.js` file so props can be reactive `$state`, as they are when App passes them.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';
import RdfPreview from './RdfPreview.svelte';

const ok = {
  scenario_id: 's1', rdf_format: 'nt', rdf: '<urn:x> <urn:y> "z" .\n', triple_count: 1,
  validation: { conforms: true, report: 'Validation Report\nConforms: True\n' },
};

/** @type {Record<string, any> | undefined} */
let component;
afterEach(() => {
  if (component) unmount(component);
  component = undefined;
  document.body.innerHTML = '';
});

/** @param {Record<string, any>} [overrides] */
function render(overrides = {}) {
  const props = $state({ json: '{"id":"s1"}', issueCount: 0, onIncomplete: () => {}, ...overrides });
  /** @type {any} */
  const anyProps = props;
  component = mount(RdfPreview, { target: document.body, props: anyProps });
  return props;
}

const button = () => /** @type {HTMLButtonElement} */ (document.querySelector('button.primary'));
const text = () => document.body.textContent ?? '';

/** @param {() => boolean} condition */
async function until(condition) {
  await vi.waitFor(() => {
    flushSync();
    if (!condition()) throw new Error('condition not met');
  });
}

/** A fetch whose response the test releases explicitly. */
function pendingFetch() {
  /** @type {(response: Response) => void} */
  let release = () => {};
  const fetch = vi.fn(() => new Promise((resolve) => { release = resolve; }));
  return { fetch, respond: (/** @type {Response} */ r) => release(r) };
}

describe('RdfPreview', () => {
  it('does not contact the backend while the form is incomplete', () => {
    const fetch = vi.fn();
    const onIncomplete = vi.fn();
    render({ issueCount: 3, fetch, onIncomplete });
    button().click();
    flushSync();
    expect(fetch).not.toHaveBeenCalled();
    expect(onIncomplete).toHaveBeenCalledOnce();
    expect(text()).toContain('3 remaining');
  });

  it('shows a loading state, then the backend RDF, and states that nothing is saved', async () => {
    const { fetch, respond } = pendingFetch();
    render({ fetch });
    button().click();
    flushSync();
    expect(button().disabled).toBe(true);
    expect(button().textContent).toContain('Validating');
    respond(new Response(JSON.stringify(ok)));
    await until(() => text().includes('Valid:'));
    expect(button().disabled).toBe(false);
    expect(text()).toContain('1 triples · not saved');
    expect(document.querySelector('pre.rdf')?.textContent).toBe(ok.rdf);
    expect(text()).toContain('Previewing does not save the scenario.');
  });

  it('hides a success once the scenario changes, including edits made during the request', async () => {
    const { fetch, respond } = pendingFetch();
    const props = render({ fetch });
    button().click();
    props.json = '{"id":"s1","edited":true}';
    respond(new Response(JSON.stringify(ok)));
    await until(() => text().includes('changed since the last preview'));
    expect(document.querySelector('pre.rdf')).toBeNull();
    expect(text()).not.toContain('Valid:');

    props.json = '{"id":"s1"}'; // The exact JSON that was validated: its result applies again.
    flushSync();
    expect(text()).toContain('Valid:');
  });

  it('lists structural issues and SHACL reports from the backend', async () => {
    const error = {
      code: 'shacl_failed', message: 'Generated RDF failed SHACL validation.',
      issues: [{ location: ['body', 'agents', 0, 'name'], message: 'String should match pattern', type: 'x' }],
      shacl_report: 'Conforms: False\nA HITeam must have at least one hi:hasGoal.',
    };
    render({ fetch: vi.fn(async () => new Response(JSON.stringify(error), { status: 422 })) });
    button().click();
    await until(() => text().includes('Not valid'));
    expect(text()).toContain('agents.0.name');
    expect(text()).toContain('A HITeam must have at least one hi:hasGoal.');
    expect(document.querySelector('pre.rdf')).toBeNull();
  });

  it('explains when the backend is unavailable', async () => {
    render({ fetch: vi.fn(async () => { throw new TypeError('fetch failed'); }) });
    button().click();
    await until(() => text().includes('Preview unavailable'));
    expect(text()).toContain('Is it running?');
  });
});
