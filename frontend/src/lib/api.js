// Client for the scenario endpoints in hi_scenario/api.py. The backend is the
// authoritative validator; this module only classifies its responses.

/**
 * @typedef {{ location: (string | number)[], message: string, type: string }} InputIssue
 * @typedef {{
 *   code: 'invalid_request' | 'invalid_vocabulary' | 'shacl_failed' | 'internal_error'
 *     | 'scenario_exists' | 'scenario_not_found' | 'graphdb_unavailable'
 *     | 'graphdb_invalid_response' | 'graphdb_configuration',
 *   message: string, issues: InputIssue[], shacl_report: string | null,
 * }} SubmissionError
 * @typedef {{
 *   scenario_id: string, rdf_format: 'nt', rdf: string, triple_count: number,
 *   validation: { conforms: true, report: string },
 * }} ScenarioPreview
 * @typedef {{
 *   scenario_id: string, repository_id: string, graph_iri: string, workbench_url: string,
 *   workbench_graph_url: string, use_case_iri: string, team_iri: string,
 * }} ScenarioLocation
 * @typedef {ScenarioLocation & { triple_count: number, validation: { conforms: true, report: string } }} SavedScenario
 * @typedef {{ iri: string, label: string | null }} AgentType
 * @typedef {AgentType & { definition: string | null }} AgentRole
 * @typedef {{ iri: string, name: string | null, types: AgentType[], roles: AgentRole[] }} TeamMember
 * @typedef {ScenarioLocation & { use_case_name: string | null, members: TeamMember[] }} TeamComposition
 * @typedef {{ kind: 'rejected', status: number, error: SubmissionError }
 *   | { kind: 'unavailable', message: string }
 *   | { kind: 'unexpected', message: string }} Failure
 * @typedef {{ kind: 'ok', preview: ScenarioPreview } | Failure} PreviewResult
 * @typedef {{ kind: 'ok', saved: SavedScenario } | Failure} SaveResult
 * @typedef {{ kind: 'ok', team: TeamComposition } | Failure} TeamResult
 * @typedef {{ fetch?: typeof globalThis.fetch, baseUrl?: string, timeoutMs?: number }} Options
 */

export const DEFAULT_API_URL = 'http://127.0.0.1:8000';
const TIMEOUT_MS = 20_000;

export function apiUrl() {
  return (import.meta.env.VITE_API_URL ?? DEFAULT_API_URL).replace(/\/+$/, '');
}

/** @param {unknown} value */
const isString = (value) => typeof value === 'string';
/** @param {unknown} value */
const isOptionalString = (value) => value === null || typeof value === 'string';

/** Links rendered as hrefs must be web URLs, never `javascript:` or similar. */
/** @param {unknown} value */
function isWebUrl(value) {
  if (typeof value !== 'string') return false;
  try {
    return ['http:', 'https:'].includes(new URL(value).protocol);
  } catch {
    return false;
  }
}

/** @param {any} body */
const isValidation = (body) => body?.validation?.conforms === true && isString(body.validation.report);

/** @param {any} body @returns {body is ScenarioPreview} */
function isPreview(body) {
  return isString(body?.rdf) && typeof body.triple_count === 'number' && isValidation(body);
}

/** @param {any} body @returns {boolean} */
function isLocation(body) {
  return (
    ['scenario_id', 'repository_id', 'graph_iri', 'use_case_iri', 'team_iri'].every((key) => isString(body?.[key])) &&
    isWebUrl(body.workbench_url) &&
    isWebUrl(body.workbench_graph_url)
  );
}

/** @param {any} body @returns {body is SavedScenario} */
function isSaved(body) {
  return isLocation(body) && typeof body.triple_count === 'number' && isValidation(body);
}

/** @param {any} body @returns {body is TeamComposition} */
function isTeam(body) {
  /** @param {any} t */
  const isType = (t) => isString(t?.iri) && isOptionalString(t.label);
  return (
    isLocation(body) &&
    isOptionalString(body.use_case_name) &&
    Array.isArray(body.members) &&
    body.members.every(
      /** @param {any} m */
      (m) =>
        isString(m?.iri) &&
        isOptionalString(m.name) &&
        Array.isArray(m.types) &&
        m.types.every(isType) &&
        Array.isArray(m.roles) &&
        m.roles.every(/** @param {any} r */ (r) => isType(r) && isOptionalString(r.definition)),
    )
  );
}

/** @param {any} body @returns {body is SubmissionError} */
function isSubmissionError(body) {
  return isString(body?.code) && isString(body.message) && Array.isArray(body.issues);
}

/**
 * Call one endpoint. Never throws: transport failures and malformed responses are values.
 * @template T
 * @param {string} method
 * @param {string} path
 * @param {object | undefined} payload
 * @param {(body: any) => body is T} isExpected
 * @param {Options} options
 * @returns {Promise<{ kind: 'ok', data: T } | Failure>}
 */
async function call(method, path, payload, isExpected, options) {
  const { fetch: send = fetch, baseUrl = apiUrl(), timeoutMs = TIMEOUT_MS } = options;
  const signal = AbortSignal.timeout(timeoutMs);

  let response;
  try {
    response = await send(`${baseUrl}${path}`, {
      method,
      ...(payload === undefined
        ? {}
        : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }),
      signal,
    });
  } catch {
    const reason = signal.aborted ? 'did not respond in time' : 'could not be reached';
    return { kind: 'unavailable', message: `The backend at ${baseUrl} ${reason}. Is it running?` };
  }

  /** @type {unknown} */
  let body;
  try {
    body = await response.json();
  } catch {
    body = undefined;
  }
  if (response.ok && isExpected(body)) return { kind: 'ok', data: body };
  if (!response.ok && isSubmissionError(body)) return { kind: 'rejected', status: response.status, error: body };
  return { kind: 'unexpected', message: `Unexpected backend response (HTTP ${response.status}).` };
}

/**
 * Validate and convert without storing anything.
 * @param {object} contract  output of toContract(...)
 * @param {Options} [options]
 * @returns {Promise<PreviewResult>}
 */
export async function requestPreview(contract, options = {}) {
  const result = await call('POST', '/scenarios/preview', contract, isPreview, options);
  return result.kind === 'ok' ? { kind: 'ok', preview: result.data } : result;
}

/**
 * Validate and save as a new, immutable scenario (create-only on the backend).
 * @param {object} contract
 * @param {Options} [options]
 * @returns {Promise<SaveResult>}
 */
export async function saveScenario(contract, options = {}) {
  const result = await call('POST', '/scenarios', contract, isSaved, { timeoutMs: 30_000, ...options });
  return result.kind === 'ok' ? { kind: 'ok', saved: result.data } : result;
}

/**
 * CQ1: team members, types, and roles of a saved scenario.
 * @param {string} scenarioId
 * @param {Options} [options]
 * @returns {Promise<TeamResult>}
 */
export async function fetchTeam(scenarioId, options = {}) {
  const path = `/scenarios/${encodeURIComponent(scenarioId)}/team`;
  const result = await call('GET', path, undefined, isTeam, options);
  return result.kind === 'ok' ? { kind: 'ok', team: result.data } : result;
}
