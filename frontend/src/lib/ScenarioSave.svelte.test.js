// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';
import ScenarioSave from './ScenarioSave.svelte';

/** @param {string} id */
const location = (id) => ({
  scenario_id: id, repository_id: 'hi', graph_iri: `urn:hi-app:graph:scenario:${id}`,
  workbench_url: 'http://127.0.0.1:7200/',
  workbench_graph_url: `http://127.0.0.1:7200/resource?uri=${encodeURIComponent(`urn:hi-app:graph:scenario:${id}`)}&role=context`,
  use_case_iri: `urn:hi-app:scenario:${id}:use-case:uc`, team_iri: `urn:hi-app:scenario:${id}:team`,
});
/** @param {string} id */
const saved = (id) => ({ ...location(id), triple_count: 32, validation: { conforms: true, report: 'Conforms: True' } });
/** @param {string} id */
const team = (id) => ({
  ...location(id), use_case_name: 'Personal assistant HI system',
  members: [
    { iri: 'urn:a', name: 'AI assistant', types: [{ iri: 'urn:t:ai', label: 'Artificial Agent' }],
      roles: [{ iri: 'urn:r:assist', label: 'System Assistant Role', definition: 'Assists.' }] },
    { iri: 'urn:h', name: 'Human user', types: [{ iri: 'urn:t:h', label: 'Human Agent' }],
      roles: [{ iri: 'urn:r:user', label: 'User Role', definition: 'Uses.' }] },
  ],
});
/** @param {string} code @param {string} message */
const error = (code, message) => ({ code, message, issues: [], shacl_report: null });
/** @param {number} status @param {unknown} body */
const json = (status, body) => new Response(JSON.stringify(body), { status });

/** @type {Record<string, any> | undefined} */
let component;
afterEach(() => {
  if (component) unmount(component);
  component = undefined;
  document.body.innerHTML = '';
});

/**
 * @param {(url: string, init: RequestInit) => Promise<Response>} handler
 * @param {Record<string, any>} [overrides]
 */
function render(handler, overrides = {}) {
  const fetch = vi.fn(handler);
  const props = $state({
    json: JSON.stringify({ id: 's1', name: 'x' }),
    issueCount: 0,
    onIncomplete: () => {},
    /** @param {string} id */
    onNewScenarioId: (id) => { props.json = JSON.stringify({ ...JSON.parse(props.json), id }); },
    fetch,
    ...overrides,
  });
  /** @type {any} */
  const anyProps = props;
  component = mount(ScenarioSave, { target: document.body, props: anyProps });
  return { props, fetch };
}

const text = () => (document.body.textContent ?? '').replace(/\s+/g, ' ');
/** @param {string} label */
function click(label) {
  const button = [...document.querySelectorAll('button')].find((b) => b.textContent?.trim() === label);
  if (!button) throw new Error(`No button "${label}" in: ${text()}`);
  button.click();
  flushSync();
}
/** @param {() => boolean} condition */
async function until(condition) {
  await vi.waitFor(() => {
    flushSync();
    if (!condition()) throw new Error(`condition not met: ${text()}`);
  });
}
/** @param {string} url @param {RequestInit} init */
const isSave = (url, init) => init.method === 'POST' && url.endsWith('/scenarios');

describe('ScenarioSave', () => {
  it('does not contact the backend while the form is incomplete', () => {
    const onIncomplete = vi.fn();
    const { fetch } = render(async () => json(201, saved('s1')), { issueCount: 2, onIncomplete });
    click('Save to GraphDB');
    expect(fetch).not.toHaveBeenCalled();
    expect(onIncomplete).toHaveBeenCalledOnce();
  });

  it('saves, then shows CQ1 and a Workbench link for that saved graph', async () => {
    const { fetch } = render(async (url, init) => (isSave(url, init) ? json(201, saved('s1')) : json(200, team('s1'))));
    click('Save to GraphDB');
    await until(() => text().includes('Saved in GraphDB'));
    expect(text()).toContain('32 triples');
    expect(document.querySelector('button.primary')).toBeNull(); // Nothing left to save.
    const link = /** @type {HTMLAnchorElement} */ (document.querySelector('a.button'));
    expect(link.href).toBe(saved('s1').workbench_graph_url);
    expect(link.target).toBe('_blank');
    expect(link.rel).toContain('noopener');

    click('Show team composition (CQ1)');
    await until(() => text().includes('2 members'));
    const rows = [...document.querySelectorAll('table.team tbody tr')].map((row) =>
      [...row.querySelectorAll('td')].map((cell) => cell.textContent?.trim()),
    );
    expect(rows).toEqual([
      ['AI assistant', 'Artificial Agent', 'System Assistant Role'],
      ['Human user', 'Human Agent', 'User Role'],
    ]);
    expect(fetch.mock.calls[1][0]).toMatch(/\/scenarios\/s1\/team$/);
  });

  it('never presents a save or team result for a modified form, and offers a new scenario instead', async () => {
    const { props, fetch } = render(async (url, init) =>
      isSave(url, init) ? json(201, saved(JSON.parse(String(init.body)).id)) : json(200, team('s1')),
    );
    click('Save to GraphDB');
    await until(() => text().includes('Saved in GraphDB'));
    click('Show team composition (CQ1)');
    await until(() => text().includes('2 members'));

    props.json = JSON.stringify({ id: 's1', name: 'edited' });
    flushSync();
    expect(text()).not.toContain('Saved in GraphDB');
    expect(document.querySelector('table.team')).toBeNull();
    expect(document.querySelector('a.button')).toBeNull();
    expect(text()).toContain('these edits are not saved');

    click('Save as new scenario');
    await until(() => text().includes('Saved in GraphDB'));
    const newId = JSON.parse(props.json).id;
    expect(newId).not.toBe('s1');
    expect(JSON.parse(String(fetch.mock.calls[2][1]?.body))).toEqual({ id: newId, name: 'edited' });
    expect(text()).toContain(`urn:hi-app:graph:scenario:${newId}`);
    expect(document.querySelector('table.team')).toBeNull(); // CQ1 of s1 does not carry over.
  });

  it('hides a result that arrives after the form changed', async () => {
    /** @type {(r: Response) => void} */
    let respond = () => {};
    const { props } = render(() => new Promise((resolve) => { respond = resolve; }));
    click('Save to GraphDB');
    props.json = JSON.stringify({ id: 's1', name: 'edited during save' });
    respond(json(201, saved('s1')));
    await until(() => text().includes('these edits are not saved'));
    expect(text()).not.toContain('Saved in GraphDB');
  });

  it('explains a 409 conflict and never retries with the same ID', async () => {
    const { props, fetch } = render(async (_url, init) => {
      const id = JSON.parse(String(init.body)).id;
      return id === 's1' ? json(409, error('scenario_exists', 'This scenario ID is already saved.')) : json(201, saved(id));
    });
    click('Save to GraphDB');
    await until(() => text().includes('already exists in GraphDB'));
    expect(text()).toContain('never overwritten');
    expect(text()).not.toContain('Saved in GraphDB');
    click('Save as new scenario');
    await until(() => text().includes('Saved in GraphDB'));
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(JSON.parse(props.json).id).not.toBe('s1');
  });

  it.each([
    [503, error('graphdb_unavailable', 'GraphDB is unavailable or the repository is not ready.'), 'Not saved: GraphDB is unavailable.'],
    [502, error('graphdb_invalid_response', 'GraphDB returned unexpected data.'), 'outcome is uncertain'],
    [500, error('internal_error', 'Scenario processing failed on the server.'), 'outcome is uncertain'],
  ])('reports HTTP %i without claiming success', async (status, body, title) => {
    render(async () => json(status, body));
    click('Save to GraphDB');
    await until(() => text().includes(title));
    expect(text()).toContain(body.message);
    expect(text()).toContain('never overwritten');
    expect(text()).not.toContain('Saved in GraphDB');
    expect(document.querySelector('button.primary')?.textContent?.trim()).toBe('Save to GraphDB');
  });

  it('shows backend validation errors', async () => {
    const body = { ...error('invalid_vocabulary', 'Unknown HINT concept: MadeUpRole') };
    render(async () => json(422, body));
    click('Save to GraphDB');
    await until(() => text().includes('Not saved: the backend rejected the scenario.'));
    expect(text()).toContain('Unknown HINT concept: MadeUpRole');
  });

  it('treats an unreachable backend as an uncertain outcome', async () => {
    render(async () => { throw new TypeError('fetch failed'); });
    click('Save to GraphDB');
    await until(() => text().includes('The save did not complete.'));
    expect(text()).toContain('may have been saved');
  });

  it('keeps a successful save visible when the CQ1 query fails', async () => {
    render(async (url, init) =>
      isSave(url, init) ? json(201, saved('s1')) : json(503, error('graphdb_unavailable', 'GraphDB is unavailable.')),
    );
    click('Save to GraphDB');
    await until(() => text().includes('Saved in GraphDB'));
    click('Show team composition (CQ1)');
    await until(() => text().includes('The team query failed. The scenario is still saved.'));
    expect(text()).toContain('Saved in GraphDB');
    expect(document.querySelector('a.button')).not.toBeNull();
  });
});
