// @vitest-environment jsdom
// Svelte App → FastAPI → RDF → SHACL, against a real backend process. Run with
// `npm run test:integration`; set PYTHON to choose the interpreter (default: ../.venv, then `python`).
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';
import example from '../../examples/s1.json';
import { requestPreview } from '../src/lib/api.js';
import { PYTHON, ROOT, closedPort, startBackend } from './backend.js';

/** @type {{ url: string, stop: () => void } | undefined} */
let backend;
let baseUrl = '';

beforeAll(async () => {
  backend = await startBackend();
  baseUrl = backend.url;
}, 60_000);

afterAll(() => {
  backend?.stop();
});

/** @type {Record<string, any> | undefined} */
let app;
afterEach(() => {
  if (app) unmount(app);
  app = undefined;
  document.body.innerHTML = '';
  vi.unstubAllEnvs();
});

/** Mount the real App against `apiUrl`. */
async function mountApp(apiUrl = baseUrl) {
  vi.stubEnv('VITE_API_URL', apiUrl);
  const { default: App } = await import('../src/App.svelte');
  app = mount(App, { target: document.body });
}

const text = () => document.body.textContent ?? '';
/** @param {string} label */
function clickButton(label) {
  const button = [...document.querySelectorAll('button')].find((b) => b.textContent?.trim() === label);
  if (!button) throw new Error(`No button "${label}"`);
  button.click();
  flushSync();
}
/** @param {() => boolean} condition */
async function until(condition) {
  await vi.waitFor(() => {
    flushSync();
    if (!condition()) throw new Error('condition not met');
  }, { timeout: 15_000, interval: 50 });
}

describe('Svelte → FastAPI → RDF → SHACL', () => {
  it('previews S1 with exactly the RDF the Python pipeline generates, and invalidates it on edit', async () => {
    // The CLI's --output file always uses LF line endings (stdout may not on Windows).
    const dir = mkdtempSync(join(tmpdir(), 'hi-preview-'));
    const output = join(dir, 's1.nt');
    const cli = spawnSync(PYTHON, ['-m', 'hi_scenario', join(ROOT, 'examples/s1.json'), '--output', output], { cwd: ROOT, encoding: 'utf-8' });
    expect(cli.status, cli.stderr).toBe(0);
    const expected = readFileSync(output, 'utf-8');
    rmSync(dir, { recursive: true });

    await mountApp();
    clickButton('Load S1 example');
    clickButton('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    expect(text()).toContain('32 triples · not saved');
    expect(document.querySelector('pre.rdf')?.textContent).toBe(expected);

    const name = /** @type {HTMLInputElement} */ (document.querySelector('#agent-human-user'));
    name.value = 'Renamed participant';
    name.dispatchEvent(new Event('input', { bubbles: true }));
    flushSync();
    expect(text()).toContain('changed since the last preview');
    expect(document.querySelector('pre.rdf')).toBeNull();

    clickButton('Validate & preview RDF');
    await until(() => text().includes('Valid:'));
    expect(document.querySelector('pre.rdf')?.textContent).toContain(
      '<urn:hi-app:scenario:s1:agent:human-user> <http://www.w3.org/2000/01/rdf-schema#label> "Renamed participant" .',
    );
  }, 30_000);

  it('blocks incomplete forms locally without calling the backend', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    await mountApp();
    clickButton('Validate & preview RDF');
    expect(text()).toContain('Complete the highlighted fields first');
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it('shows an unavailable backend in the UI', async () => {
    await mountApp(`http://127.0.0.1:${await closedPort()}`);
    clickButton('Load S1 example');
    clickButton('Validate & preview RDF');
    await until(() => text().includes('Preview unavailable'));
    expect(text()).toContain('could not be reached');
    expect(document.querySelector('pre.rdf')).toBeNull();
  });

  it('returns the backend authoritative rejections that local checks cannot see', async () => {
    const vocabulary = structuredClone(example);
    vocabulary.agents[0].roles = ['MadeUpRole'];
    expect(await requestPreview(vocabulary, { baseUrl })).toEqual({
      kind: 'rejected',
      status: 422,
      error: expect.objectContaining({ code: 'invalid_vocabulary', message: 'Unknown HINT concept: MadeUpRole' }),
    });

    /** @type {any} */
    const structure = structuredClone(example);
    delete structure.goal;
    const result = await requestPreview(structure, { baseUrl });
    expect(result.kind).toBe('rejected');
    if (result.kind === 'rejected') {
      expect(result.error.code).toBe('invalid_request');
      expect(result.error.issues).toContainEqual(expect.objectContaining({ location: ['body', 'goal'] }));
    }
  });

  it('allows the Vite development origin through CORS, and only that origin', async () => {
    /** @param {string} origin */
    const preflight = (origin) =>
      fetch(`${baseUrl}/scenarios/preview`, {
        method: 'OPTIONS',
        headers: { Origin: origin, 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'content-type' },
      });
    const allowed = await preflight('http://localhost:5173');
    expect(allowed.status).toBe(200);
    expect(allowed.headers.get('access-control-allow-origin')).toBe('http://localhost:5173');
    const other = await preflight('http://localhost:5174');
    expect(other.headers.get('access-control-allow-origin')).toBeNull();
  });
});
