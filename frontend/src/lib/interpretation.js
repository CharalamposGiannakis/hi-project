export const questions = /** @type {const} */ ([
  { id: 'use_case', title: 'Use case', prompt: 'What situation are you investigating, and in which domain?' },
  { id: 'goal', title: 'Goal', prompt: 'What does the team aim to achieve?' },
  { id: 'tasks', title: 'Tasks', prompt: 'What tasks are involved, and which ones are required to achieve the goal?' },
  { id: 'agents', title: 'Team members and roles', prompt: 'Who or what is on the team, and what role does each member play?' },
  { id: 'capabilities', title: 'Agent capabilities', prompt: 'What can each team member do, and which tasks does that capability support?' },
  { id: 'context', title: 'Context', prompt: 'What conditions, events, or constraints shape the setting in which the team operates?' },
  { id: 'team_constraints', title: 'Team constraints', prompt: 'What rules or limits apply to the team as a whole?' },
  { id: 'executions', title: 'Task executions and methods', prompt: 'Who performs each task in practice, and how do they do it?' },
  { id: 'interactions', title: 'Interactions', prompt: 'Which team members interact, for what purpose, and through which channel?' },
  { id: 'experiments', title: 'Experiments and hypotheses', prompt: 'What experiment would you run, and which hypotheses would it test?' },
  { id: 'evaluations', title: 'Evaluations and metrics', prompt: 'How would you evaluate the results, and which measurements would you use?' },
  { id: 'additional_notes', title: 'Additional notes', prompt: 'What else should a reader know, including uncertainties or open questions?' },
]);

/**
 * @typedef {typeof questions[number]['id']} QuestionId
 * @typedef {Partial<Record<QuestionId, string>>} Answers
 * @typedef {'complete' | 'incomplete'} ModelStatus
 * @typedef {'not_interpreted' | 'simulated_complete' | 'simulated_incomplete' | 'unsupported'} LegacyStatus
 * @typedef {{ kind?: DiagnosticKind, message: string, path?: string }} InterpretationDiagnostic
 * @typedef {{ status: ModelStatus, model: string, prompt_version: string, diagnostics: InterpretationDiagnostic[] }} ModelInterpretation
 * @typedef {(ModelInterpretation & { source_description: Answers, generated_scenario: Record<string, unknown> | null })
 *   | { status: LegacyStatus, diagnostics: InterpretationDiagnostic[], source_description?: never, generated_scenario?: never }} InterpretationRecord
 * @typedef {InterpretationRecord & { source_changed?: true, scenario_changed?: true }} Interpretation
 * @typedef {{ scenario: Record<string, unknown> | null, interpretation: ModelInterpretation }} InterpretationResponse
 */

export const diagnosticLabels = {
  missing_information: 'Missing information',
  ambiguity: 'Ambiguity',
  unsupported_vocabulary: 'Vocabulary suggestion',
  unsupported_relationship: 'Unsupported relationship',
  structural: 'Structural issue',
  technical_validation: 'Technical validation issue',
};

/** @typedef {keyof typeof diagnosticLabels} DiagnosticKind */

const complete = /** @satisfies {Answers} */ ({
  use_case: 'A personal assistant HI system for health and lifestyle.',
  goal: 'Maintain and improve user wellbeing.',
  tasks: 'The goal requires collecting user self-reports and sensor-based activity data.',
  agents: 'The team has two members: a human user and an AI assistant, each acting in that role.',
  context: 'In a health-monitoring setting, sensor noise can affect measurements. User privacy is a constraint in this setting.',
});

export const sampleDescriptions = {
  complete,
  incomplete: { ...complete, agents: 'A human user is on the team in the role of user. Other team members are still to be determined.' },
};

/** @param {Answers} answers @param {Record<string, unknown> | null} scenario @param {Interpretation} interpretation */
export function createInterpretationDocument(answers, scenario, interpretation) {
  return { source_description: { ...answers }, scenario, interpretation };
}

/** @param {unknown} value @returns {value is Record<string, unknown>} */
function isRecord(value) {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** @param {unknown} value @returns {value is Answers} */
function isAnswers(value) {
  return isRecord(value) && Object.entries(value).every(([key, answer]) =>
    questions.some(({ id }) => id === key) && typeof answer === 'string');
}

/** @param {unknown} value @returns {value is LegacyStatus} */
function isLegacyStatus(value) {
  return value === 'not_interpreted' || value === 'simulated_complete' || value === 'simulated_incomplete' || value === 'unsupported';
}

/** @param {unknown} value @returns {value is InterpretationDiagnostic} */
function isDiagnostic(value) {
  return isRecord(value) && typeof value.message === 'string'
    && (!Object.hasOwn(value, 'path') || typeof value.path === 'string')
    && (!Object.hasOwn(value, 'kind') || (typeof value.kind === 'string' && Object.hasOwn(diagnosticLabels, value.kind)));
}

/** @param {unknown} value @returns {value is ModelInterpretation} */
function isModelInterpretation(value) {
  return isRecord(value) && (value.status === 'complete' || value.status === 'incomplete')
    && typeof value.model === 'string' && value.model.length > 0
    && typeof value.prompt_version === 'string' && value.prompt_version.length > 0
    && Array.isArray(value.diagnostics) && value.diagnostics.every((diagnostic) => isDiagnostic(diagnostic) && diagnostic.kind !== undefined);
}

/** @param {unknown} value @returns {value is InterpretationResponse} */
export function isInterpretationResponse(value) {
  return isRecord(value) && (value.scenario === null || isRecord(value.scenario))
    && isModelInterpretation(value.interpretation)
    && (value.scenario !== null || value.interpretation.status === 'incomplete');
}

/**
 * Recognize the guided document while leaving canonical scenario parsing to the existing editor.
 * @param {unknown} value
 * @returns {{ source_description: Answers, scenario: Record<string, unknown> | null, interpretation: Interpretation } | null}
 */
export function readInterpretationDocument(value) {
  if (!isRecord(value) || !(Object.hasOwn(value, 'source_description') || Object.hasOwn(value, 'interpretation'))) return null;

  const { source_description: source, scenario, interpretation } = value;
  if (!isAnswers(source)) {
    throw new Error('The source description must contain text answers for known wizard questions.');
  }
  if (scenario !== null && !isRecord(scenario)) throw new Error('The scenario must be an object or null.');
  if (!isRecord(interpretation) || (Object.hasOwn(interpretation, 'source_changed') && interpretation.source_changed !== true)
      || (Object.hasOwn(interpretation, 'scenario_changed') && interpretation.scenario_changed !== true)) {
    throw new Error('The interpretation must contain a recognized status and a list of diagnostics.');
  }

  const { source_changed: sourceChanged, scenario_changed: scenarioChanged, source_description: sentDescription,
    generated_scenario: generated, status, diagnostics } = interpretation;
  /** @type {InterpretationRecord} */
  let record;
  if (isModelInterpretation(interpretation)) {
    if (!isAnswers(sentDescription) || (generated !== null && !isRecord(generated))
        || (generated === null && interpretation.status === 'complete')) {
      throw new Error('The interpretation must include the sent description and generated scenario.');
    }
    const { status, model, prompt_version, diagnostics } = interpretation;
    record = { status, model, prompt_version, diagnostics, source_description: sentDescription, generated_scenario: generated };
  } else if (isLegacyStatus(status) && Array.isArray(diagnostics) && diagnostics.every(isDiagnostic)) {
    record = { status, diagnostics };
  } else {
    throw new Error('The interpretation must contain a recognized status and a list of diagnostics.');
  }
  return {
    source_description: source,
    scenario,
    interpretation: { ...record, ...(sourceChanged ? { source_changed: true } : {}), ...(scenarioChanged ? { scenario_changed: true } : {}) },
  };
}
