// Shared helpers for integration tests: spawn the real FastAPI backend.
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { createServer } from 'node:net';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
export const PYTHON =
  process.env.PYTHON ??
  [join(ROOT, '.venv/Scripts/python.exe'), join(ROOT, '.venv/bin/python')].find(existsSync) ??
  'python';

/**
 * Start uvicorn on a free port; resolves with its URL and a stop function.
 * @param {Record<string, string>} [env]  extra environment, e.g. GRAPHDB_URL
 * @returns {Promise<{ url: string, stop: () => void }>}
 */
export function startBackend(env = {}) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(
      PYTHON,
      ['-m', 'uvicorn', 'hi_scenario.api:app', '--host', '127.0.0.1', '--port', '0', '--no-use-colors'],
      { cwd: ROOT, env: { ...process.env, ...env }, stdio: ['ignore', 'ignore', 'pipe'] },
    );
    let log = '';
    child.on('error', reject);
    child.on('exit', (code) => reject(new Error(`Backend exited (${code}):\n${log}`)));
    child.stderr?.on('data', (chunk) => {
      log += chunk;
      const match = log.match(/Uvicorn running on (http:\/\/127\.0\.0\.1:\d+)/);
      if (match) resolvePromise({ url: match[1], stop: () => child.kill() });
    });
  });
}

/** A local port with nothing listening on it. @returns {Promise<number>} */
export function closedPort() {
  return new Promise((resolvePromise) => {
    const server = createServer().listen(0, '127.0.0.1', () => {
      const address = /** @type {import('node:net').AddressInfo} */ (server.address());
      server.close(() => resolvePromise(address.port));
    });
  });
}
