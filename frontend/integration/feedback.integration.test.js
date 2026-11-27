// @vitest-environment jsdom
// Real form → FastAPI → private filesystem → operator export/restore. No GraphDB or Nebula.
import { spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';
import App from '../src/App.svelte';
import { PYTHON, ROOT, startBackend } from './backend.js';

const temporary = mkdtempSync(join(tmpdir(), 'hi-feedback-integration-'));
const directory = join(temporary, 'private-feedback');
/** @type {{url: string, stop: () => void} | undefined} */
let backend;
/** @type {Record<string, any> | undefined} */
let app;

beforeAll(async () => {
  backend = await startBackend({ FEEDBACK_DIR: directory, NEBULA_API_KEY: '', HI_NEBULA_LIVE: '0' });
}, 60_000);
afterEach(async () => {
  if (app) await unmount(app);
  app = undefined;
  document.body.innerHTML = '';
  vi.unstubAllEnvs();
});
afterAll(() => {
  backend?.stop();
  rmSync(temporary, { recursive: true, force: true });
});

it('stores explicit feedback from Home, retains Builder work, and supports private operator recovery', async () => {
  vi.stubEnv('VITE_API_URL', backend?.url);
  app = mount(App, { target: document.body });
  flushSync();
  const click = (/** @type {string} */ label) => {
    const button = [...document.querySelectorAll('button')].find((button) => button.textContent?.trim() === label);
    if (!button) throw new Error(`Missing button: ${label}`);
    button.click();
    flushSync();
  };
  click('Scenario Builder');
  click('Load S1 example');
  const draft = document.querySelector('pre.json')?.textContent;
  click('Home');
  click('Share feedback');
  const message = /** @type {HTMLTextAreaElement} */ (document.getElementById('feedback-message'));
  message.value = 'Synthetic preview feedback: the task explanation could be clearer.';
  message.dispatchEvent(new Event('input', { bubbles: true }));
  flushSync();
  click('Send feedback');
  await vi.waitFor(() => {
    flushSync();
    expect(document.querySelector('#feedback-view [role=status]')?.textContent).toContain('Feedback saved');
  }, { timeout: 10_000 });

  const operator = (/** @type {string} */ action, target = directory, /** @type {string | undefined} */ input = undefined) => spawnSync(
    PYTHON, ['-m', 'infra.feedback', action],
    { cwd: ROOT, env: { ...process.env, FEEDBACK_DIR: target }, input, encoding: 'utf8', timeout: 20_000 },
  );
  const exported = operator('export');
  expect(exported.status).toBe(0);
  const bundle = JSON.parse(exported.stdout);
  expect(bundle.records).toHaveLength(1);
  expect(bundle.records[0]).toMatchObject({ category: 'problem', area: 'general', message: 'Synthetic preview feedback: the task explanation could be clearer.' });
  expect(Object.keys(bundle.records[0]).sort()).toEqual(['area', 'category', 'created_at', 'id', 'message']);
  const restored = operator('restore', join(temporary, 'restored'), exported.stdout);
  expect(restored.status).toBe(0);
  expect(JSON.parse(operator('export', join(temporary, 'restored')).stdout)).toEqual(bundle);
  expect((await fetch(`${backend?.url}/feedback`)).status).toBe(405);
  expect((await fetch(`${backend?.url}/feedback/${bundle.records[0].id}`)).status).toBe(404);
  click('Scenario Builder');
  expect(document.querySelector('pre.json')?.textContent).toBe(draft);
}, 30_000);
