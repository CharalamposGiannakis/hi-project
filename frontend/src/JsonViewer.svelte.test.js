// @vitest-environment jsdom
import { BroadcastChannel as NativeBroadcastChannel } from 'node:worker_threads';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';
import JsonViewer from './JsonViewer.svelte';
import { createJsonSource, JSON_REQUEST_TIMEOUT_MS } from './lib/json-viewer-channel.js';
import s7 from '../../examples/s7.json';

/** @type {Record<string, any> | undefined} */
let viewer;
/** @type {ReturnType<typeof createJsonSource> | undefined} */
let source;
let json = JSON.stringify(s7);
beforeEach(() => {
  vi.stubGlobal('BroadcastChannel', NativeBroadcastChannel);
  json = JSON.stringify(s7);
  source = createJsonSource(() => json);
  window.history.replaceState(null, '', `/json-viewer.html#${source.id}`);
});
afterEach(async () => {
  if (viewer) await unmount(viewer);
  viewer = undefined;
  source?.close();
  source = undefined;
  document.body.innerHTML = '';
  window.history.replaceState(null, '', '/');
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
function render() {
  viewer = mount(JsonViewer, { target: document.body });
  flushSync();
}
const pre = () => document.querySelector('pre');
const button = () => /** @type {HTMLButtonElement} */ (document.querySelector('button'));
/** @param {() => void} assertion */
async function until(assertion) {
  await vi.waitFor(() => { flushSync(); assertion(); });
}

describe('separate JSON viewer', () => {
  it('retrieves complete formatted S7 on opening and only refreshes edits on demand', async () => {
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    render();
    expect(button().disabled).toBe(true);
    expect(document.body.textContent).toContain('Retrieving the latest JSON');
    await until(() => expect(pre()?.textContent).toBe(JSON.stringify(s7, null, 2)));
    expect(button().disabled).toBe(false);
    expect(document.body.textContent).toContain('Keep the original Scenario Builder tab open');
    expect(document.body.textContent).toContain('do not update this snapshot automatically');
    const edited = structuredClone(s7);
    edited.tasks[2].name = 'Unsaved research task';
    json = JSON.stringify(edited);
    expect(pre()?.textContent).toBe(JSON.stringify(s7, null, 2));
    button().click();
    flushSync();
    expect(document.body.textContent).toContain('Previous snapshot — latest state not confirmed');
    await until(() => expect(pre()?.textContent).toBe(JSON.stringify(edited, null, 2)));
    expect(document.querySelector('[role=status]')?.textContent).toContain('Snapshot retrieved');
    expect(pre()?.getAttribute('tabindex')).toBe('0');
    expect(pre()?.hasAttribute('contenteditable')).toBe(false);
    expect(document.querySelector('textarea')).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('retrieves fresh state after remounting at the same URL, without browser storage', async () => {
    const storage = vi.spyOn(Storage.prototype, 'setItem');
    render();
    await until(() => expect(pre()).not.toBeNull());
    await unmount(/** @type {Record<string, any>} */ (viewer));
    viewer = undefined;
    document.body.innerHTML = '';
    json = JSON.stringify({ ...s7, id: 'new-draft' });
    render();
    expect(pre()).toBeNull();
    await until(() => expect(JSON.parse(pre()?.textContent ?? '{}').id).toBe('new-draft'));
    expect(window.location.pathname).toBe('/json-viewer.html');
    expect(window.location.search).toBe('');
    expect(storage).not.toHaveBeenCalled();
  });

  it('marks an older snapshot after the Builder closes and lets the researcher retry', async () => {
    render();
    await until(() => expect(pre()).not.toBeNull());
    source?.close();
    vi.useFakeTimers();
    button().click();
    flushSync();
    await vi.advanceTimersByTimeAsync(JSON_REQUEST_TIMEOUT_MS);
    flushSync();
    expect(document.querySelector('[role=alert]')?.textContent).toContain('may be closed or unavailable');
    expect(document.body.textContent).toContain('Previous snapshot — latest state not confirmed');
    expect(document.body.textContent).toContain('may be out of date');
    expect(JSON.parse(pre()?.textContent ?? '{}')).toEqual(s7);
    expect(button().disabled).toBe(false);
    button().click();
    flushSync();
    expect(document.body.textContent).toContain('Retrieving the latest JSON');
    await vi.advanceTimersByTimeAsync(JSON_REQUEST_TIMEOUT_MS);
    flushSync();
    expect(button().disabled).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('shows a clear error with no snapshot when the Builder is unavailable on opening', async () => {
    source?.close();
    vi.useFakeTimers();
    render();
    await vi.advanceTimersByTimeAsync(JSON_REQUEST_TIMEOUT_MS);
    flushSync();
    expect(document.querySelector('[role=alert]')?.textContent).toContain('Could not retrieve JSON');
    expect(pre()).toBeNull();
    expect(button().disabled).toBe(false);
  });

  it('handles missing connection links or unavailable browser communication', async () => {
    window.history.replaceState(null, '', '/json-viewer.html');
    render();
    await until(() => expect(document.querySelector('[role=alert]')?.textContent).toContain('Open this viewer using'));
    expect(pre()).toBeNull();
    await unmount(/** @type {Record<string, any>} */ (viewer));
    viewer = undefined;
    document.body.innerHTML = '';
    window.history.replaceState(null, '', `/json-viewer.html#${source?.id}`);
    vi.stubGlobal('BroadcastChannel', undefined);
    render();
    await until(() => expect(document.querySelector('[role=alert]')?.textContent).toContain('Could not retrieve JSON'));
    expect(button().disabled).toBe(false);
    vi.stubGlobal('BroadcastChannel', NativeBroadcastChannel);
    button().click();
    await until(() => expect(JSON.parse(pre()?.textContent ?? '{}')).toEqual(s7));
  });

  it('renders HTML-looking scenario values as text and cancels communication on unmount', async () => {
    json = JSON.stringify({ ...s7, use_case: { ...s7.use_case, name: '<img src=x onerror="alert(1)">' } });
    render();
    await until(() => expect(pre()?.textContent).toContain('<img'));
    expect(document.querySelector('img')).toBeNull();
    expect(document.querySelector('script')).toBeNull();
    source?.close();
    vi.useFakeTimers();
    const close = vi.spyOn(NativeBroadcastChannel.prototype, 'close');
    button().click();
    flushSync();
    await unmount(/** @type {Record<string, any>} */ (viewer));
    viewer = undefined;
    expect(close).toHaveBeenCalledOnce();
    // Svelte also schedules deferred unmount work, separate from our request timer.
    await vi.runOnlyPendingTimersAsync();
    expect(vi.getTimerCount()).toBe(0);
  });
});
