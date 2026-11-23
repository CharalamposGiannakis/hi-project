// Client for the scenario endpoints in hi_scenario/api.py. The backend is the
// authoritative validator; this module only classifies its responses.
import { isInterpretationResponse } from './interpretation.js';
import { concepts } from './scenario.js';

/**
 * @typedef {{ location: (string | number)[], message: string, type: string }} InputIssue
 * @typedef {{
 *   code: 'invalid_request' | 'invalid_vocabulary' | 'shacl_failed' | 'internal_error'
 *     | 'scenario_exists' | 'scenario_id_reserved' | 'scenario_not_found' | 'graphdb_unavailable'
 *     | 'graphdb_invalid_response' | 'graphdb_configuration' | 'interpretation_unavailable' | 'interpretation_failed',
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
 * @typedef {'cq1' | 'cq2' | 'cq5' | 'cq8' | 'cq11'} ExplorerQuestionId
 * @typedef {'draft' | 'shared' | 'combined'} ExplorerScope
 * @typedef {'approved' | 'reference' | 'provisional'} PublicationStatus
 * @typedef {{ id: string, scenario_id: string, name: string, description: string | null,
 *   publication_status: PublicationStatus, graph_iri: string }} ExplorerSource
 * @typedef {{ id: string, label: string, category: import('./scenario.js').Category }} ExplorerParameter
 * @typedef {{ id: ExplorerQuestionId, label: string, description: string, parameters: ExplorerParameter[] }} ExplorerQuestion
 * @typedef {{ shared_source: 'approved' | 'reference', scenarios: ExplorerSource[], questions: ExplorerQuestion[], warnings?: string[] }} ExplorerCatalog
 * @typedef {{ question_id: ExplorerQuestionId, scope: ExplorerScope, scenario?: object,
 *   shared_scenario_id?: string, parameters?: Record<string, string> }} ExplorerRequest
 * @typedef {'Capability' | 'Constraint' | 'Method' | 'Metric'} ExplorationCategory
 * @typedef {{ scope: ExplorerScope, scenario?: object, shared_scenario_id?: string,
 *   category?: ExplorationCategory | null, concept?: string | null, compare?: boolean }} ConceptExplorationRequest
 * @typedef {{ id: string, label: string }} ExplorerColumn
 * @typedef {{ label: string, iri: string }} ExplorerEvidence
 * @typedef {{ source_id: string, values: Record<string, string | null>, evidence: ExplorerEvidence[] }} ExplorerRow
 * @typedef {{ code: string, message: string, source_id?: string | null }} ExplorerNotice
 * @typedef {{ sources: ExplorerSource[], columns: ExplorerColumn[], rows: ExplorerRow[], truncated: boolean, notices?: ExplorerNotice[] }} ExplorerResults
 * @typedef {{ fetch?: typeof globalThis.fetch, baseUrl?: string, timeoutMs?: number, signal?: AbortSignal }} Options
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

/** @param {any} source @returns {source is ExplorerSource} */
function isExplorerSource(source) {
  return isString(source?.id) && isString(source.scenario_id) && isString(source.name)
    && isOptionalString(source.description) && isString(source.graph_iri)
    && ['approved', 'reference', 'provisional'].includes(source.publication_status);
}

/** @param {any} question @returns {question is ExplorerQuestion} */
function isExplorerQuestion(question) {
  const { id, label, description, parameters } = question ?? {};
  return ['cq1', 'cq2', 'cq5', 'cq8', 'cq11'].includes(id)
    && isString(label) && isString(description) && Array.isArray(parameters)
    && parameters.every((parameter) => isString(parameter?.id) && isString(parameter.label)
      && typeof parameter.category === 'string' && Object.hasOwn(concepts, parameter.category));
}

/** @param {any} body @returns {body is ExplorerCatalog} */
function isExplorerCatalog(body) {
  return ['approved', 'reference'].includes(body?.shared_source)
    && Array.isArray(body.scenarios) && body.scenarios.every(isExplorerSource)
    && Array.isArray(body.questions) && body.questions.every(isExplorerQuestion)
    && (body.warnings === undefined || (Array.isArray(body.warnings) && body.warnings.every(isString)));
}

/** @param {any} row @returns {row is ExplorerRow} */
function isExplorerRow(row) {
  const { source_id, values, evidence } = row ?? {};
  return isString(source_id) && values && typeof values === 'object' && !Array.isArray(values)
    && Object.values(values).every(isOptionalString) && Array.isArray(evidence)
    && evidence.every((item) => isString(item?.label) && isString(item.iri));
}

/** @param {any} body @returns {body is ExplorerResults} */
function isExplorerResults(body) {
  const { truncated, sources, columns, rows } = body ?? {};
  return typeof truncated === 'boolean' && Array.isArray(sources) && sources.every(isExplorerSource)
    && Array.isArray(columns) && columns.every((column) => isString(column?.id) && isString(column.label))
    && Array.isArray(rows) && rows.every((row) => isExplorerRow(row)
      && sources.some((source) => source.id === row.source_id))
    && (body.notices === undefined || (Array.isArray(body.notices) && body.notices.every(
      (/** @type {any} */ notice) => isString(notice?.code) && isString(notice.message)
        && (notice.source_id == null || sources.some((source) => source.id === notice.source_id)),
    )));
}

/** @param {any} body @returns {body is SubmissionError} */
function isSubmissionError(body) {
  return isString(body?.code) && isString(body.message) && Array.isArray(body.issues) &&
    body.issues.every((/** @type {any} */ issue) =>
      Array.isArray(issue?.location) && issue.location.every((/** @type {unknown} */ part) => isString(part) || Number.isInteger(part)) &&
      isString(issue.message) && isString(issue.type));
}

/** @param {(string | number)[]} location */
export function issuePath(location) {
  return (location[0] === 'body' ? location.slice(1) : location).join('.') || 'scenario';
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
  const { fetch: send = fetch, baseUrl = apiUrl(), timeoutMs = TIMEOUT_MS, signal: callerSignal } = options;
  const timeout = AbortSignal.timeout(timeoutMs);
  const signal = callerSignal ? AbortSignal.any([callerSignal, timeout]) : timeout;

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
    const reason = timeout.aborted ? 'did not respond in time' : 'could not be reached';
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
 * Request an interpretation of the supplied wizard text.
 * @param {import('./interpretation.js').Answers} description
 * @param {Options} [options]
 */
export function requestInterpretation(description, options = {}) {
  return call('POST', '/scenarios/interpret', { description }, isInterpretationResponse, { timeoutMs: 140_000, ...options });
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

/** @param {Options} [options] */
export function fetchExplorerCatalog(options = {}) {
  return call('GET', '/explorer/catalog', undefined, isExplorerCatalog, options);
}

/** @param {ExplorerRequest} request @param {Options} [options] */
export function requestExplorerQuery(request, options = {}) {
  return call('POST', '/explorer/query', request, isExplorerResults, options);
}

/** @param {ConceptExplorationRequest} request @param {Options} [options] */
export function requestConceptExploration(request, options = {}) {
  return call('POST', '/explorer/concepts', request, isExplorerResults, options);
}
