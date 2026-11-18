import s1 from '../../../examples/s1.json';
import { fromContract, toContract } from './scenario.js';

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
 * @typedef {'not_interpreted' | 'simulated_complete' | 'simulated_incomplete' | 'unsupported'} InterpretationStatus
 * @typedef {{ message: string, path?: string }} InterpretationDiagnostic
 * @typedef {{ status: InterpretationStatus, diagnostics: InterpretationDiagnostic[], source_changed?: true }} Interpretation
 * @typedef {ReturnType<typeof toContract>} ScenarioContract
 */

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

/** @param {Answers} answers @param {Answers} sample */
function matchesSample(answers, sample) {
  return questions.every(({ id }) => (answers[id] ?? '').trim() === (sample[id] ?? ''));
}

/**
 * This fixture maps only facts present in the supplied samples using the S1 vocabulary choices.
 * @param {Answers} answers
 * @returns {{ scenario: ScenarioContract | null, interpretation: Interpretation }}
 */
export function simulateInterpretation(answers) {
  const isComplete = matchesSample(answers, sampleDescriptions.complete);
  if (!isComplete && !matchesSample(answers, sampleDescriptions.incomplete)) {
    return {
      scenario: null,
      interpretation: {
        status: 'unsupported',
        diagnostics: [{ message: 'The simulator supports the two sample descriptions. Use the Structured Editor to enter your own scenario.' }],
      },
    };
  }

  const task = s1.tasks[0];
  const { id, name, concept } = s1.goal;
  const scenario = fromContract({
    id: crypto.randomUUID(),
    use_case: s1.use_case,
    goal: { id, name, concept, required_tasks: [task.id] },
    tasks: [task],
    agents: isComplete ? s1.agents : s1.agents.filter((agent) => agent.kind === 'human'),
    context: {
      concept: s1.context.concept,
      phenomena: ['SensorNoisePhenomenon'],
      constraints: ['PrivacyConstraint'],
    },
  }, { allowDraft: !isComplete });

  return {
    scenario: toContract(scenario),
    interpretation: {
      status: isComplete ? 'simulated_complete' : 'simulated_incomplete',
      diagnostics: isComplete ? [] : [{ path: 'agents', message: 'The description did not identify an artificial team member or its role.' }],
    },
  };
}

/** @param {Answers} answers @param {ScenarioContract | null} scenario @param {Interpretation} interpretation */
export function createInterpretationDocument(answers, scenario, interpretation) {
  return { source_description: { ...answers }, scenario, interpretation };
}

/** @param {unknown} value @returns {value is Record<string, unknown>} */
function isRecord(value) {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** @param {unknown} value @returns {value is InterpretationStatus} */
function isStatus(value) {
  return value === 'not_interpreted' || value === 'simulated_complete' || value === 'simulated_incomplete' || value === 'unsupported';
}

/** @param {unknown} value @returns {value is InterpretationDiagnostic} */
function isDiagnostic(value) {
  return isRecord(value) && typeof value.message === 'string' && (!Object.hasOwn(value, 'path') || typeof value.path === 'string');
}

/**
 * Recognize the guided document while leaving canonical scenario parsing to the existing editor.
 * @param {unknown} value
 * @returns {{ source_description: Answers, scenario: Record<string, unknown> | null, interpretation: Interpretation } | null}
 */
export function readInterpretationDocument(value) {
  if (!isRecord(value) || !(Object.hasOwn(value, 'source_description') || Object.hasOwn(value, 'interpretation'))) return null;

  const { source_description: source, scenario, interpretation } = value;
  if (!isRecord(source) || Object.entries(source).some(([key, answer]) =>
    !questions.some(({ id }) => id === key) || typeof answer !== 'string')) {
    throw new Error('The source description must contain text answers for known wizard questions.');
  }
  if (scenario !== null && !isRecord(scenario)) throw new Error('The scenario must be an object or null.');
  if (!isRecord(interpretation) || !isStatus(interpretation.status)
      || !Array.isArray(interpretation.diagnostics) || !interpretation.diagnostics.every(isDiagnostic)
      || (Object.hasOwn(interpretation, 'source_changed') && interpretation.source_changed !== true)) {
    throw new Error('The interpretation must contain a recognized status and a list of diagnostics.');
  }

  const { status, diagnostics, source_changed: sourceChanged } = interpretation;
  return {
    source_description: source,
    scenario,
    interpretation: { status, diagnostics, ...(sourceChanged ? { source_changed: true } : {}) },
  };
}
