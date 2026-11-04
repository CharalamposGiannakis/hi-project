import { describe, expect, it } from 'vitest';
import { concepts } from './scenario.js';
import { vocabularyLabel } from './vocabulary-labels.js';

describe('vocabulary display labels', () => {
  it.each([
    ['UseCase', 'Personal Assistant Use Case', 'Personal Assistant'],
    ['Domain', 'Education Domain', 'Education'],
    ['Capability', 'Clinical judgment capability', 'Clinical judgment'],
    ['TaskExecution', 'Data Collection Task Execution', 'Data Collection'],
    ['InteractionModality', 'Text Chat Modality', 'Text Chat'],
    ['Evaluation', 'Evaluation', 'Evaluation'],
    ['Goal', 'Accurate and Trustworthy Diagnosis', 'Accurate and Trustworthy Diagnosis'],
    ['Phenomenon', 'Explanation Message Feedback', 'Explanation Message Feedback'],
    ['Task', 'Domain', 'Domain'],
    ['Domain', 'Domain knowledge', 'Domain knowledge'],
  ])('shortens %s labels only when the category is redundant', (category, label, expected) => {
    expect(vocabularyLabel(/** @type {import('./scenario.js').Category} */ (category), label)).toBe(expected);
  });

  it('retains a canonical label when shortening would create ambiguity', () => {
    concepts.Domain.push({ id: 'test-only', label: 'Education', definition: '' });
    try {
      expect(vocabularyLabel('Domain', 'Education Domain')).toBe('Education Domain');
    } finally { concepts.Domain.pop(); }
  });

  it('leaves the complete vocabulary unchanged with nonempty, distinct display labels', () => {
    const before = JSON.stringify(concepts);
    for (const category of /** @type {import('./scenario.js').Category[]} */ (Object.keys(concepts))) {
      const labels = concepts[category].map((concept) => vocabularyLabel(category, concept.label));
      expect(labels.every((label) => label.trim().length > 0)).toBe(true);
      expect(new Set(labels).size).toBe(labels.length);
    }
    expect(JSON.stringify(concepts)).toBe(before);
  });
});
