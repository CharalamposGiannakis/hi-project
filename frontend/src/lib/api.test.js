import { describe, expect, it, vi } from 'vitest';
import { requestPreview } from './api.js';

const preview = {
  scenario_id: 's1', rdf_format: 'nt', rdf: '<a> <b> <c> .\n', triple_count: 1,
  validation: { conforms: true, report: 'Conforms: True' },
};

/** @param {number} status @param {unknown} body */
const reply = (status, body) =>
  vi.fn(async () => new Response(typeof body === 'string' ? body : JSON.stringify(body), { status }));

describe('requestPreview', () => {
  it('posts the contract JSON to /scenarios/preview', async () => {
    const fetch = reply(200, preview);
    const result = await requestPreview({ id: 's1' }, { fetch, baseUrl: 'http://api.test' });
    expect(result).toEqual({ kind: 'ok', preview });
    const [url, init] = /** @type {any} */ (fetch.mock.calls[0]);
    expect(url).toBe('http://api.test/scenarios/preview');
    expect(init.method).toBe('POST');
    expect(init.headers).toEqual({ 'Content-Type': 'application/json' });
    expect(JSON.parse(init.body)).toEqual({ id: 's1' });
  });

  it.each([
    [422, { code: 'invalid_request', message: 'Bad', issues: [{ location: ['body', 'goal'], message: 'missing', type: 'missing' }], shacl_report: null }],
    [422, { code: 'shacl_failed', message: 'SHACL', issues: [], shacl_report: 'Conforms: False' }],
    [500, { code: 'internal_error', message: 'Failed', issues: [], shacl_report: null }],
  ])('returns backend rejections unchanged (%i)', async (status, error) => {
    expect(await requestPreview({}, { fetch: reply(status, error) })).toEqual({ kind: 'rejected', error });
  });

  it('reports an unreachable backend', async () => {
    const fetch = vi.fn(async () => { throw new TypeError('fetch failed'); });
    const result = await requestPreview({}, { fetch, baseUrl: 'http://api.test' });
    expect(result).toEqual({ kind: 'unavailable', message: expect.stringContaining('could not be reached') });
  });

  it('reports a timeout', async () => {
    /** @type {typeof globalThis.fetch} */
    const hanging = (_url, init) =>
      new Promise((_, reject) => init?.signal?.addEventListener('abort', () => reject(init.signal?.reason)));
    const result = await requestPreview({}, { fetch: hanging, timeoutMs: 10 });
    expect(result).toEqual({ kind: 'unavailable', message: expect.stringContaining('did not respond in time') });
  });

  it.each([
    [200, 'not json'],
    [200, { ...preview, validation: { conforms: false, report: '' } }],
    [404, { detail: 'Not Found' }],
    [502, '<html>Bad gateway</html>'],
  ])('treats malformed or foreign responses as unexpected (%i)', async (status, body) => {
    const result = await requestPreview({}, { fetch: reply(status, body) });
    expect(result).toEqual({ kind: 'unexpected', message: `Unexpected backend response (HTTP ${status}).` });
  });
});
