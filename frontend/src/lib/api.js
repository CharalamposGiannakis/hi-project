// Client for POST /scenarios/preview (hi_scenario/api.py). The backend is the
// authoritative validator; this module only classifies its responses.

/**
 * @typedef {{ location: (string | number)[], message: string, type: string }} InputIssue
 * @typedef {{
 *   code: 'invalid_request' | 'invalid_vocabulary' | 'shacl_failed' | 'internal_error',
 *   message: string, issues: InputIssue[], shacl_report: string | null,
 * }} SubmissionError
 * @typedef {{
 *   scenario_id: string, rdf_format: 'nt', rdf: string, triple_count: number,
 *   validation: { conforms: true, report: string },
 * }} ScenarioPreview
 * @typedef {{ kind: 'ok', preview: ScenarioPreview }
 *   | { kind: 'rejected', error: SubmissionError }
 *   | { kind: 'unavailable', message: string }
 *   | { kind: 'unexpected', message: string }} PreviewResult
 */

export const DEFAULT_API_URL = 'http://127.0.0.1:8000';
const TIMEOUT_MS = 20_000;

export function apiUrl() {
  return (import.meta.env.VITE_API_URL || DEFAULT_API_URL).replace(/\/+$/, '');
}

/** @param {any} body @returns {body is ScenarioPreview} */
function isPreview(body) {
  return (
    typeof body?.rdf === 'string' &&
    typeof body.triple_count === 'number' &&
    body.validation?.conforms === true &&
    typeof body.validation.report === 'string'
  );
}

/** @param {any} body @returns {body is SubmissionError} */
function isSubmissionError(body) {
  return typeof body?.code === 'string' && typeof body.message === 'string' && Array.isArray(body.issues);
}

/**
 * Send contract JSON to the backend. Never throws: every outcome is a PreviewResult.
 * @param {object} contract  output of toContract(...)
 * @param {{ fetch?: typeof fetch, baseUrl?: string, timeoutMs?: number }} [options]
 * @returns {Promise<PreviewResult>}
 */
export async function requestPreview(contract, options = {}) {
  const { fetch: send = fetch, baseUrl = apiUrl(), timeoutMs = TIMEOUT_MS } = options;
  const signal = AbortSignal.timeout(timeoutMs);

  let response;
  try {
    response = await send(`${baseUrl}/scenarios/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(contract),
      signal,
    });
  } catch {
    const reason = signal.aborted ? 'did not respond in time' : 'could not be reached';
    return { kind: 'unavailable', message: `The validation backend at ${baseUrl} ${reason}. Is it running?` };
  }

  /** @type {unknown} */
  let body;
  try {
    body = await response.json();
  } catch {
    body = undefined;
  }
  if (response.ok && isPreview(body)) return { kind: 'ok', preview: body };
  if (!response.ok && isSubmissionError(body)) return { kind: 'rejected', error: body };
  return { kind: 'unexpected', message: `Unexpected backend response (HTTP ${response.status}).` };
}
