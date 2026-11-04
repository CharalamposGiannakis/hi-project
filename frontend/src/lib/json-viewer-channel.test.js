import { BroadcastChannel as NativeBroadcastChannel } from 'node:worker_threads';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createJsonSource, JSON_REQUEST_TIMEOUT_MS, requestScenarioJson } from './json-viewer-channel.js';

/** @type {ReturnType<typeof createJsonSource>[]} */
const sources = [];
beforeEach(() => vi.stubGlobal('BroadcastChannel', NativeBroadcastChannel));
afterEach(() => {
  sources.splice(0).forEach((source) => source.close());
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

/** @param {() => string} getJson */
function source(getJson) {
  const source = createJsonSource(getJson);
  sources.push(source);
  return source;
}

describe('on-demand JSON communication over native BroadcastChannel', () => {
  it('reads unsaved state at each request and sends no unsolicited updates', async () => {
    let json = '{"id":"draft","name":"Initial"}';
    const read = vi.fn(() => json);
    const builder = source(read);
    expect(read).not.toHaveBeenCalled();
    const first = await requestScenarioJson(builder.id);
    expect(JSON.parse(first).name).toBe('Initial');
    json = '{"id":"draft","name":"Unsaved edit"}';
    expect(read).toHaveBeenCalledTimes(1);
    expect(JSON.parse(first).name).toBe('Initial');
    expect(JSON.parse(await requestScenarioJson(builder.id)).name).toBe('Unsaved edit');
    expect(read).toHaveBeenCalledTimes(2);
  });

  it('isolates Builder instances and concurrent viewers even when scenario IDs match', async () => {
    const first = source(() => '{"id":"s7","name":"First Builder"}');
    const second = source(() => '{"id":"s7","name":"Second Builder"}');
    expect(first.id).not.toBe(second.id);
    const snapshots = await Promise.all([
      requestScenarioJson(first.id), requestScenarioJson(second.id), requestScenarioJson(first.id),
    ]);
    expect(snapshots.map((json) => JSON.parse(json).name)).toEqual(['First Builder', 'Second Builder', 'First Builder']);
  });

  it('times out after the Builder closes and closes the request channel', async () => {
    const builder = source(() => '{"id":"s7"}');
    builder.close();
    vi.useFakeTimers();
    const close = vi.spyOn(NativeBroadcastChannel.prototype, 'close');
    const result = requestScenarioJson(builder.id).catch((error) => error);
    await vi.advanceTimersByTimeAsync(JSON_REQUEST_TIMEOUT_MS);
    expect(await result).toBeInstanceOf(Error);
    expect(close).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('ignores responses for other requests and accepts only valid JSON text', async () => {
    const id = crypto.randomUUID();
    const peer = new NativeBroadcastChannel(`hi-scenario-json:${id}`);
    peer.onmessage = ({ data }) => {
      peer.postMessage({ type: 'scenario-json', requestId: 'unrelated', json: '{"wrong":true}' });
      peer.postMessage({ type: 'scenario-json', requestId: data.requestId, json: '{"correct":true}' });
    };
    try { expect(JSON.parse(await requestScenarioJson(id))).toEqual({ correct: true }); }
    finally { peer.close(); }
  });

  it('rejects a malformed snapshot and supports an abort without leaving timers or channels', async () => {
    const builder = source(() => 'not json');
    await expect(requestScenarioJson(builder.id)).rejects.toThrow();
    vi.useFakeTimers();
    const close = vi.spyOn(NativeBroadcastChannel.prototype, 'close');
    const controller = new AbortController();
    const result = requestScenarioJson(crypto.randomUUID(), { signal: controller.signal }).catch((error) => error);
    controller.abort();
    expect((await result).name).toBe('AbortError');
    expect(close).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('reports unavailable communication and rejects missing connections without creating a channel', async () => {
    const unavailable = vi.fn(function () { throw new Error('Unavailable'); });
    vi.stubGlobal('BroadcastChannel', unavailable);
    await expect(requestScenarioJson('')).rejects.toThrow();
    expect(unavailable).not.toHaveBeenCalled();
    await expect(requestScenarioJson(crypto.randomUUID())).rejects.toThrow('Unavailable');
  });
});
