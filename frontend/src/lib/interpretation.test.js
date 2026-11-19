import { describe, expect, it } from 'vitest';
import s1 from '../../../examples/s1.json';
import {
  createInterpretationDocument,
  readInterpretationDocument,
} from './interpretation.js';
import { fromContract, validate } from './scenario.js';

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

  it('round-trips generated provenance separately from the editable draft', () => {
    const generated = { ...s1, agents: [{ ...s1.agents[0], kind: '' }] };
    const candidate = { ...generated, agents: [{ ...generated.agents[0], kind: 'human' }] };
    const sentDescription = { use_case: '  Early idea\n' };
    const answers = { ...sentDescription, additional_notes: 'Assistant role under discussion.' };
    const document = createInterpretationDocument(answers, candidate, {
      status: 'incomplete', model: 'test-model', prompt_version: 'test-v1',
      prompt_sha256: 'b'.repeat(64),
      source_description: sentDescription, generated_scenario: generated,
      diagnostics: [{ kind: 'missing_information', message: 'Agent type is missing.', path: 'agents.0.kind' }],
      source_changed: true, scenario_changed: true,
    });
    expect(readInterpretationDocument(JSON.parse(JSON.stringify(document)))).toEqual(document);
    expect(readInterpretationDocument(s1)).toBeNull();
  });

  it('accepts Phase 1A.1 drafts without model provenance', () => {
    const legacy = createInterpretationDocument({ use_case: 'Edited description' }, s1, {
      status: 'simulated_incomplete', source_changed: true, diagnostics: [{ message: 'The agent role is missing.' }],
    });
    expect(readInterpretationDocument(legacy)).toEqual(legacy);
  });

  it('accepts downloaded Nebula drafts from before prompt hashes were recorded', () => {
    const answers = { use_case: 'An older description' };
    const olderDraft = createInterpretationDocument(answers, s1, {
      status: 'complete', model: 'test-model', prompt_version: 'test-v1', diagnostics: [],
      source_description: answers, generated_scenario: s1,
    });
    expect(readInterpretationDocument(olderDraft)).toEqual(olderDraft);
    const malformed = { ...olderDraft, interpretation: { ...olderDraft.interpretation, prompt_sha256: 'invalid' } };
    expect(() => readInterpretationDocument(malformed)).toThrow();
  });

  it('leaves omitted goal links unresolved in drafts and rejects duplicate editor identities', () => {
    const draft = fromContract(s1, { allowDraft: true });
    expect(draft.goal.required_tasks).toEqual([]);
    expect(validate(draft)).toContainEqual(expect.objectContaining({ path: 'goal.required_tasks' }));
    const duplicates = { ...s1, tasks: [s1.tasks[0], s1.tasks[0]] };
    expect(() => fromContract(duplicates, { allowDraft: true })).toThrow('duplicate entity IDs');
  });

  it('preserves an unspecified agent kind only in an editable draft', () => {
    const scenario = { ...s1, agents: [{ ...s1.agents[0], kind: '' }, s1.agents[1]] };
    const editor = fromContract(scenario, { allowDraft: true });
    expect(editor.agents[0].kind).toBe('');
    expect(validate(editor)).toContainEqual(expect.objectContaining({ path: 'agents.0.kind' }));
    expect(() => fromContract(scenario)).toThrow('agents.0.kind');
  });

  it.each([
    { source_description: { typo: 'a description' } },
    { source_description: { goal: 10 } },
    { scenario: [] },
    { interpretation: { status: 'unknown', diagnostics: [] } },
    { interpretation: { status: 'unsupported', diagnostics: [{ message: 'See agents', path: 2 }] } },
    { interpretation: { status: 'complete', model: 'test-model', prompt_version: 'v1', diagnostics: [] } },
  ])('rejects malformed interpretation documents (%j)', (fields) => {
    const document = createInterpretationDocument({}, null, { status: 'not_interpreted', diagnostics: [] });
    expect(() => readInterpretationDocument({ ...document, ...fields })).toThrow();
  });
});
