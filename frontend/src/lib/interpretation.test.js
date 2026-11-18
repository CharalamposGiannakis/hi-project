import { describe, expect, it } from 'vitest';
import {
  createInterpretationDocument,
  readInterpretationDocument,
  sampleDescriptions,
  simulateInterpretation,
} from './interpretation.js';
import { fromContract, validate } from './scenario.js';

describe('simulated interpretation', () => {
  it('uses canonical entities and explicit goal-task links for the complete sample', () => {
    const { scenario, interpretation } = simulateInterpretation(sampleDescriptions.complete);
    expect(interpretation).toEqual({ status: 'simulated_complete', diagnostics: [] });
    const loaded = fromContract(scenario);
    expect(loaded.goal.required_tasks).toEqual(loaded.tasks.map(({ id }) => id));
    expect(loaded.agents.map(({ kind }) => kind)).toEqual(['human', 'artificial']);
    expect(loaded.context?.constraints).toEqual(['PrivacyConstraint']);
  });

  it('returns a useful partial candidate without supplying the missing team member', () => {
    const { scenario, interpretation } = simulateInterpretation(sampleDescriptions.incomplete);
    expect(interpretation).toMatchObject({ status: 'simulated_incomplete', diagnostics: [{ path: 'agents' }] });
    expect(scenario).toMatchObject({
      agents: [{ name: 'Human user', kind: 'human' }],
      tasks: [{ id: 'data-collection' }],
    });
    expect(() => fromContract(scenario)).toThrow('The team needs at least one human and one artificial agent.');
  });

  it('keeps custom descriptions separate from fixture scenario facts', () => {
    const answers = { ...sampleDescriptions.complete, additional_notes: 'The assistant would also coach the user.' };
    const { scenario, interpretation } = simulateInterpretation(answers);
    expect(scenario).toBeNull();
    expect(interpretation.status).toBe('unsupported');
    expect(interpretation.diagnostics).toHaveLength(1);
    expect(createInterpretationDocument(answers, scenario, interpretation).source_description).toEqual(answers);
  });
});

describe('interpretation document', () => {
  it('round-trips the exact source text with no candidate or prior interpretation', () => {
    const answers = { use_case: '  Early idea\n', additional_notes: 'Roles undecided.' };
    const document = createInterpretationDocument(answers, null, { status: 'not_interpreted', diagnostics: [] });
    expect(readInterpretationDocument(JSON.parse(JSON.stringify(document)))).toEqual({
      source_description: answers,
      scenario: null,
      interpretation: { status: 'not_interpreted', diagnostics: [] },
    });
  });

  it('preserves incomplete candidates and marks interpretations based on earlier source text', () => {
    const { scenario, interpretation } = simulateInterpretation(sampleDescriptions.incomplete);
    const answers = { ...sampleDescriptions.incomplete, additional_notes: 'Still considering the assistant.' };
    const document = createInterpretationDocument(answers, scenario, { ...interpretation, source_changed: true });
    expect(readInterpretationDocument(JSON.parse(JSON.stringify(document)))).toEqual(document);
    expect(readInterpretationDocument(scenario)).toBeNull();
  });

  it('leaves omitted goal links unresolved in drafts and rejects duplicate editor identities', () => {
    const { scenario } = simulateInterpretation(sampleDescriptions.complete);
    if (!scenario) throw new Error('Missing complete sample');
    const { required_tasks: _omitted, ...goal } = scenario.goal;
    const draft = fromContract({ ...scenario, goal }, { allowDraft: true });
    expect(draft.goal.required_tasks).toEqual([]);
    expect(validate(draft)).toContainEqual(expect.objectContaining({ path: 'goal.required_tasks' }));
    const duplicates = { ...scenario, tasks: [scenario.tasks[0], scenario.tasks[0]] };
    expect(() => fromContract(duplicates, { allowDraft: true })).toThrow('duplicate entity IDs');
  });

  it.each([
    { source_description: { typo: 'a description' } },
    { source_description: { goal: 10 } },
    { scenario: [] },
    { interpretation: { status: 'unknown', diagnostics: [] } },
    { interpretation: { status: 'unsupported', diagnostics: [{ message: 'See agents', path: 2 }] } },
  ])('rejects malformed interpretation documents (%j)', (fields) => {
    const document = createInterpretationDocument({}, null, { status: 'not_interpreted', diagnostics: [] });
    expect(() => readInterpretationDocument({ ...document, ...fields })).toThrow();
  });
});
