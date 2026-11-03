import { concepts } from './scenario.js';

// Only remove the category already established by a field or section heading.
const suffixes = {
  UseCase: 'Use Case', Domain: 'Domain', Goal: 'Goal', Task: 'Task', Role: 'Role',
  Context: 'Context', Phenomenon: 'Phenomenon', Constraint: 'Constraint',
  Capability: 'Capability', TaskExecution: 'Task Execution', Method: 'Method',
  Experiment: 'Experiment', Evaluation: 'Evaluation', Metric: 'Metric',
  InteractionIntent: 'Intent', InteractionModality: 'Modality',
};

/** @param {import('./scenario.js').Category} category @param {string} label */
export function vocabularyLabel(category, label) {
  const suffix = new RegExp(` ${suffixes[category]}$`, 'i');
  /** @param {string} text */
  const shorten = (text) => text.replace(suffix, '').trim() || text;
  const short = shorten(label);
  // Retain the full label if shortening would make two concepts indistinguishable.
  return concepts[category].some((concept) => concept.label !== label && shorten(concept.label).toLowerCase() === short.toLowerCase())
    ? label : short;
}
