import { describe, expect, it, vi } from 'vitest';
import { apiUrl, fetchTeam, requestPreview, saveScenario } from './api.js';

it('uses a relative API route when the deployed bundle requests it', () => {
  vi.stubEnv('VITE_API_URL', '/api');
  expect(apiUrl()).toBe('/api');
  vi.unstubAllEnvs();
});

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
    expect(await requestPreview({}, { fetch: reply(status, error) })).toEqual({ kind: 'rejected', status, error });
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

const location = {
  scenario_id: 's1', repository_id: 'hi', graph_iri: 'urn:hi-app:graph:scenario:s1',
  workbench_url: 'http://127.0.0.1:7200/',
  workbench_graph_url: 'http://127.0.0.1:7200/resource?uri=urn%3Ahi-app%3Agraph%3Ascenario%3As1&role=context',
  use_case_iri: 'urn:hi-app:scenario:s1:use-case:personal-assistant', team_iri: 'urn:hi-app:scenario:s1:team',
};
const saved = { ...location, triple_count: 32, validation: { conforms: true, report: 'Conforms: True' } };
const team = {
  ...location, use_case_name: 'Personal assistant HI system',
  members: [{
    iri: 'urn:hi-app:scenario:s1:agent:human-user', name: 'Human user',
    types: [{ iri: 'https://w3id.org/hi-ontology#HumanAgent', label: 'Human Agent' }],
    roles: [{ iri: 'https://w3id.org/hi-thesaurus/HumanUserRole', label: 'User Role', definition: null }],
  }],
};

describe('saveScenario', () => {
  it('posts to /scenarios and accepts a 201 location', async () => {
    const fetch = reply(201, saved);
    expect(await saveScenario({ id: 's1' }, { fetch, baseUrl: 'http://api.test' })).toEqual({ kind: 'ok', saved });
    const [url, init] = /** @type {any} */ (fetch.mock.calls[0]);
    expect(url).toBe('http://api.test/scenarios');
    expect(init.method).toBe('POST');
  });

  it.each([[409, 'scenario_exists'], [503, 'graphdb_unavailable'], [502, 'graphdb_invalid_response']])(
    'keeps the status of rejections (%i)',
    async (status, code) => {
      const error = { code, message: 'm', issues: [], shacl_report: null };
      expect(await saveScenario({}, { fetch: reply(status, error) })).toEqual({ kind: 'rejected', status, error });
    },
  );

  it('rejects responses whose Workbench link is not a web URL', async () => {
    const result = await saveScenario({}, { fetch: reply(201, { ...saved, workbench_graph_url: 'javascript:alert(1)' }) });
    expect(result.kind).toBe('unexpected');
  });
});

describe('fetchTeam', () => {
  it('GETs the CQ1 endpoint with an encoded ID and no body', async () => {
    const fetch = reply(200, team);
    expect(await fetchTeam('s1', { fetch, baseUrl: 'http://api.test' })).toEqual({ kind: 'ok', team });
    const [url, init] = /** @type {any} */ (fetch.mock.calls[0]);
    expect(url).toBe('http://api.test/scenarios/s1/team');
    expect(init.method).toBe('GET');
    expect(init.body).toBeUndefined();
    await fetchTeam('a/b?c', { fetch, baseUrl: 'http://api.test' });
    expect(/** @type {any} */ (fetch.mock.calls[1])[0]).toBe('http://api.test/scenarios/a%2Fb%3Fc/team');
  });

  it('treats malformed members as unexpected', async () => {
    const result = await fetchTeam('s1', { fetch: reply(200, { ...team, members: [{ iri: 1 }] }) });
    expect(result.kind).toBe('unexpected');
  });
});
