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
