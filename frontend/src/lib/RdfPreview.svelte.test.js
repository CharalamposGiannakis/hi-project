// @vitest-environment jsdom
// A `.svelte.test.js` file so props can be reactive `$state`, as they are when App passes them.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';
import RdfPreview from './RdfPreview.svelte';

const ok = {
  scenario_id: 's1', rdf_format: 'nt', rdf: '<urn:x> <urn:y> "z" .\n', triple_count: 1,
  validation: { conforms: true, report: 'Validation Report\nConforms: True\n' },
};
const shaclError = {
  code: 'shacl_failed', message: 'Generated RDF failed SHACL validation.',
  issues: [{ location: ['body', 'agents', 0, 'name'], message: 'String should match pattern', type: 'x' }],
  shacl_report: 'Conforms: False\nA HITeam must have at least one hi:hasGoal.',
};

/** @type {ReturnType<typeof mount> | undefined} */
let component;
afterEach(async () => {
  if (component) await unmount(component);
  component = undefined;
  document.body.innerHTML = '';
});

/** @param {Partial<import('svelte').ComponentProps<typeof RdfPreview>>} [overrides] */
function render(overrides = {}) {
  const props = $state({ target: { contract: { id: 's1' } }, issueCount: 0, onIncomplete: () => {}, ...overrides });
  component = mount(RdfPreview, { target: document.body, props });
  flushSync();
  return props;
}

const button = () => /** @type {HTMLButtonElement} */ (document.querySelector('button.primary'));
const addButton = () => [...document.querySelectorAll('button')]
  .find((control) => control.textContent === 'Add to Knowledge Explorer →');
const status = () => document.querySelector('[data-validation-status]')?.textContent;
const text = () => document.body.textContent ?? '';

/** @param {string} expected */
async function waitForStatus(expected) {
  await vi.waitFor(() => {
    flushSync();
    expect(status()).toBe(expected);
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
  it('adds an independent snapshot of the exact payload that passed validation', async () => {
    const { fetch, respond } = pendingFetch();
    const onAddToExplorer = vi.fn();
    const contract = { id: 's1', agents: [{ name: 'Original member' }] };
    render({ target: { contract }, fetch, onAddToExplorer });
    expect(addButton()).toBeUndefined();
    button().click();
    flushSync();
    expect(addButton()).toBeUndefined();
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/scenarios/preview'),
      expect.objectContaining({ body: JSON.stringify(contract) }));
    respond(new Response(JSON.stringify(ok)));
    await waitForStatus('Valid');
    expect(onAddToExplorer).not.toHaveBeenCalled();

    addButton()?.click();
    const first = onAddToExplorer.mock.calls[0][0];
    expect(first).toEqual(contract);
    expect(first).not.toBe(contract);
    expect(first.agents).not.toBe(contract.agents);
    first.agents[0].name = 'Changed returned copy';
    addButton()?.click();
    expect(onAddToExplorer.mock.calls[1][0].agents[0].name).toBe('Original member');
    expect(contract.agents[0].name).toBe('Original member');
  });

  it('blocks adding stale, incomplete, and rejected scenarios until current validation succeeds', async () => {
    const onAddToExplorer = vi.fn();
    const fetch = vi.fn(async () => new Response(JSON.stringify(ok)));
    const props = render({ fetch, onAddToExplorer });
    button().click();
    await waitForStatus('Valid');
    expect(addButton()).toBeDefined();
    props.target = { contract: { id: 's1', edited: true } };
    flushSync();
    expect(addButton()).toBeUndefined();
    props.issueCount = 1;
    button().click();
    flushSync();
    expect(status()).toBe('Needs corrections');
    expect(addButton()).toBeUndefined();

    props.issueCount = 0;
    props.fetch = vi.fn(async () => new Response(JSON.stringify(shaclError), { status: 422 }));
    button().click();
    await waitForStatus('Needs corrections');
    expect(addButton()).toBeUndefined();
    expect(onAddToExplorer).not.toHaveBeenCalled();
  });

  it('does not offer an in-flight successful result for an edited scenario', async () => {
    const { fetch, respond } = pendingFetch();
    const onAddToExplorer = vi.fn();
    const props = render({ fetch, onAddToExplorer });
    button().click();
    flushSync();
    props.target = { contract: { id: 'new-revision' } };
    respond(new Response(JSON.stringify(ok)));
    await waitForStatus('Not validated');
    expect(addButton()).toBeUndefined();
    expect(onAddToExplorer).not.toHaveBeenCalled();
  });

  it('does not contact the backend while the form is incomplete', () => {
    const fetch = vi.fn();
    const onIncomplete = vi.fn();
    render({ issueCount: 3, fetch, onIncomplete });
    expect(status()).toBe('Not validated');
    expect(button().textContent).toBe('Validate Scenario');
    button().click();
    flushSync();
    expect(fetch).not.toHaveBeenCalled();
    expect(onIncomplete).toHaveBeenCalledOnce();
    expect(status()).toBe('Needs corrections');
    expect(text()).toContain('Review the highlighted fields');
  });

  it('validates on request and exposes RDF and the SHACL report after success', async () => {
    const { fetch, respond } = pendingFetch();
    render({ fetch });
    expect(fetch).not.toHaveBeenCalled();
    button().click();
    flushSync();
    expect(button().disabled).toBe(true);
    expect(status()).toBe('Validating…');
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/scenarios/preview'),
      expect.objectContaining({ method: 'POST', body: '{"id":"s1"}' }));

    respond(new Response(JSON.stringify(ok)));
    await waitForStatus('Valid');
    expect(button().disabled).toBe(false);
    expect(text()).toContain('Generated 1 triple.');
    expect(text()).toContain('Scientific approval requires a separate review.');
    const rdfPreview = [...document.querySelectorAll('summary')].find((element) => element.textContent === 'RDF preview');
    rdfPreview?.click();
    expect(rdfPreview?.closest('details')?.open).toBe(true);
    expect(document.querySelector('pre.rdf')?.textContent).toBe(ok.rdf);
    expect(document.querySelector('pre.report')?.textContent).toBe(ok.validation.report);
  });

  it('requires fresh validation after an edit and after reverting to the same contract', async () => {
    const props = render({ fetch: vi.fn(async () => new Response(JSON.stringify(ok))) });
    button().click();
    await waitForStatus('Valid');

    props.target = { contract: { id: 's1', edited: true } };
    flushSync();
    expect(status()).toBe('Not validated');
    expect(text()).toContain('The scenario has changed.');
    expect(document.querySelector('pre.rdf')).toBeNull();

    props.target = { contract: { id: 's1' } };
    flushSync();
    expect(status()).toBe('Not validated');
    expect(document.querySelector('pre.rdf')).toBeNull();

    button().click();
    await waitForStatus('Valid');
  });

  it('discards in-flight results and field diagnostics once the scenario changes', async () => {
    const { fetch, respond } = pendingFetch();
    const onValidationIssues = vi.fn();
    const props = render({ fetch, onValidationIssues });
    button().click();
    flushSync();
    expect(status()).toBe('Validating…');
    props.target = { contract: { id: 's1', edited: true } };
    respond(new Response(JSON.stringify(shaclError), { status: 422 }));
    await waitForStatus('Not validated');
    expect(button().disabled).toBe(false);
    expect(onValidationIssues).toHaveBeenCalledOnce();
    expect(onValidationIssues).toHaveBeenCalledWith([], { contract: { id: 's1' } });
    expect(document.querySelector('pre.report')).toBeNull();
  });

  it('forwards current field issues to the editor and displays the backend SHACL report', async () => {
    const onValidationIssues = vi.fn();
    const fetch = vi.fn(async () => new Response(JSON.stringify(shaclError), { status: 422 }));
    const props = render({ fetch, onValidationIssues });
    button().click();
    await waitForStatus('Needs corrections');
    expect(onValidationIssues).toHaveBeenLastCalledWith(shaclError.issues, props.target);
    expect(text()).toContain(shaclError.message);
    expect(document.querySelector('pre.report')?.textContent).toBe(shaclError.shacl_report);
    expect(document.querySelector('pre.rdf')).toBeNull();
  });

  it('explains when the backend is unavailable', async () => {
    render({ fetch: vi.fn(async () => { throw new TypeError('fetch failed'); }) });
    button().click();
    await waitForStatus('Technical validation error');
    expect(text()).toContain('Is it running?');
  });
});
