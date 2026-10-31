import { describe, expect, it } from 'vitest';
import legacyExample from '../../../examples/s1.json';
import s2 from '../../../examples/s2.json';
import s3 from '../../../examples/s3.json';
import s4 from '../../../examples/s4.json';
import s5 from '../../../examples/s5.json';
import s6 from '../../../examples/s6.json';
import { concepts, emptyScenario, fromContract, newAgent, newCapability, newContext, newExecution, newExperiment, newEvaluation, newInteraction, newId, newTask, removeEntity, toContract, validate } from './scenario.js';

const ID = /^[a-z0-9][a-z0-9_-]*$/;
const example = { ...legacyExample, goal: { ...legacyExample.goal, required_tasks: legacyExample.tasks.map((task) => task.id) } };
const copy = () => structuredClone(example);

describe('S6 reconstruction', () => {
  it('round-trips shared entities, separate episodes, exact HINT identifiers, and plain hypotheses', () => {
    const scenario = fromContract(JSON.stringify(s6));
    expect(validate(scenario)).toEqual([]);
    expect(toContract(fromContract(JSON.stringify(toContract(scenario))))).toEqual(s6);
    expect(scenario.tasks).toHaveLength(5);
    expect(scenario.goal.required_tasks).toEqual(scenario.tasks.map((task) => task.id));
    expect(scenario.capabilities).toHaveLength(5);
    expect(scenario.capabilities.find((capability) => capability.id === 'explaining')?.agents).toEqual(['ai-building-agent', 'human-grid-operator']);
    expect(scenario.executions).toHaveLength(6);
    expect(scenario.executions.filter((execution) => execution.task === 'explain-decision').map((execution) => execution.agent)).toEqual(['ai-building-agent', 'human-grid-operator']);
    expect(scenario.evaluations).toHaveLength(1);
    expect(scenario.evaluations[0].executions).toEqual(scenario.executions.map((execution) => execution.id));
    expect(scenario.evaluations[0].metrics).toEqual(s6.experiments[0].metrics);
    expect(scenario.experiments).toHaveLength(1);
    expect(scenario.experiments[0].metrics).toHaveLength(4);
    expect(scenario.experiments[0].hypothesis_language).toBe('');
    expect(toContract(scenario).experiments?.[0]).not.toHaveProperty('hypothesis_language');
    expect(scenario.interactions.map((interaction) => [interaction.id, interaction.executions])).toEqual([
      ['negotiation', ['negotiate']], ['explain-allocation', ['explain-decision']],
    ]);
    expect(scenario.interactions.every((interaction) => interaction.agents.length === 2 && !interaction.executions.includes('explain-operator'))).toBe(true);
    expect(scenario.tasks.find((task) => task.id === 'negotiate-allocation')?.concept).toBe('AllocationNegotationTask');
    expect(scenario.evaluations[0].concept).toBe('NegotationImpactEvaluation');
  });
});

describe('S5 reconstruction', () => {
  it('offers generic Evaluation and round-trips distinct evaluations, shared capability, episodes, and literals', () => {
    expect(concepts.Evaluation.find((concept) => concept.id === 'Evaluation')?.label).toBe('Evaluation');
    const scenario = fromContract(JSON.stringify(s5));
    expect(validate(scenario)).toEqual([]);
    expect(toContract(fromContract(JSON.stringify(toContract(scenario))))).toEqual(s5);
    expect(scenario.goal.required_tasks).toEqual(scenario.tasks.map((task) => task.id));
    expect(scenario.capabilities).toHaveLength(4);
    expect(scenario.capabilities.find((capability) => capability.id === 'explaining')?.agents).toEqual(['ai-diagnostic-assistant', 'human-clinician']);
    expect(scenario.executions).toHaveLength(5);
    expect(scenario.executions.filter((execution) => execution.task === 'explain-reasoning').map((execution) => execution.agent)).toEqual(['ai-diagnostic-assistant', 'human-clinician']);
    expect(scenario.evaluations.map((evaluation) => evaluation.concept)).toEqual(['Evaluation', 'Evaluation']);
    expect(new Set(scenario.evaluations.map((evaluation) => evaluation.id)).size).toBe(2);
    expect(scenario.evaluations.map((evaluation) => evaluation.executions)).toEqual([
      ['symptom-embedding', 'candidate-generation', 'hypothesis-comparison'], ['explain-ai', 'explain-human'],
    ]);
    expect(scenario.evaluations.map((evaluation) => evaluation.experiment)).toEqual(['diagnosis-accuracy', 'explanation-clarity']);
    expect(scenario.experiments.map((experiment) => experiment.hypothesis_language)).toEqual(['en', 'en']);
    expect(scenario.interactions[0].executions).toEqual(['explain-ai', 'explain-human']);
    expect([scenario.context?.description, ...scenario.experiments.map((e) => e.description), ...scenario.evaluations.map((e) => e.description), scenario.interactions[0].description].every(Boolean)).toBe(true);
  });

  it.each(['DiagnosisAccuracyMetric', 'ExplanationClarityMetric'])('still rejects %s as an Evaluation concept', (metric) => {
    const source = structuredClone(s5);
    source.evaluations[0].concept = metric;
    expect(() => fromContract(source)).toThrow('not a HINT Evaluation concept');
    const scenario = fromContract(s5);
    scenario.evaluations[0].concept = metric;
    expect(validate(scenario).map((issue) => issue.path)).toContain('evaluations.0.concept');
  });
});

describe('S4 reconstruction', () => {
  it('round-trips descriptions, repeated task realizations, shared evaluation, and the linked interaction', () => {
    const scenario = fromContract(JSON.stringify(s4));
    expect(validate(scenario)).toEqual([]);
    expect(toContract(fromContract(JSON.stringify(toContract(scenario))))).toEqual(s4);
    expect(scenario.tasks).toHaveLength(6);
    expect(scenario.goal.required_tasks).toEqual(scenario.tasks.map((task) => task.id));
    expect(scenario.tasks.map((task) => task.description)).toEqual(s4.tasks.map((task) => task.description));
    expect(scenario.context?.description).toBe(s4.context.description);
    expect(scenario.capabilities).toHaveLength(5);
    expect(scenario.capabilities.find((capability) => capability.id === 'semantic-reasoning')?.tasks).toEqual(['semantic-reasoning', 'recommend-resources']);
    expect(scenario.executions).toHaveLength(6);
    expect(scenario.executions.filter((execution) => execution.task === 'reconstruct-trajectory').map((execution) => execution.agent)).toEqual(['human-learner', 'ai-tutor']);
    expect(scenario.executions.some((execution) => execution.task === 'kg-query')).toBe(false);
    expect(scenario.evaluations).toHaveLength(1);
    expect(scenario.evaluations[0].executions).toEqual(scenario.executions.map((execution) => execution.id));
    expect(scenario.evaluations[0].metrics).toEqual(s4.experiments[0].metrics);
    expect(scenario.experiments[0].metrics).toHaveLength(3);
    expect(scenario.experiments[0].hypothesis_language).toBe('en');
    expect(scenario.interactions).toHaveLength(1);
    expect(scenario.interactions[0].executions).toEqual(['explain-recommendations']);
  });
});

describe('S3 reconstruction', () => {
  it('round-trips distinct jurors, shared entities, unlinked interactions, and English hypotheses', () => {
    const scenario = fromContract(JSON.stringify(s3));
    expect(validate(scenario)).toEqual([]);
    expect(toContract(scenario)).toEqual(s3);
    expect(scenario.agents.filter((agent) => agent.kind === 'human').map((agent) => agent.id)).toEqual(['human-juror-1', 'human-juror-2']);
    expect(scenario.capabilities).toHaveLength(4);
    expect(scenario.capabilities.find((capability) => capability.id === 'self-reporting')?.agents).toEqual(['human-juror-1', 'human-juror-2']);
    expect(scenario.goal.required_tasks).toEqual(scenario.tasks.map((task) => task.id));
    expect(scenario.executions).toHaveLength(5);
    expect(scenario.executions.filter((execution) => execution.task === 'provide-statement').map((execution) => execution.agent)).toEqual(['human-juror-1', 'human-juror-2']);
    expect(scenario.evaluations).toHaveLength(1);
    expect(scenario.evaluations[0].executions).toEqual(scenario.executions.map((execution) => execution.id));
    expect(scenario.evaluations[0].metrics).toHaveLength(3);
    expect(scenario.experiments).toHaveLength(1);
    expect(scenario.experiments[0].metrics).toHaveLength(3);
    expect(scenario.experiments[0].hypothesis_language).toBe('en');
    expect(scenario.interactions).toHaveLength(2);
    expect(scenario.interactions.every((interaction) => interaction.agents.length === 3 && interaction.executions.length === 0)).toBe(true);
    expect(scenario.tasks[0].concept).toBe('AssessCommunicationAccuracy');
  });

  it('continues to reject the original undefined concept instead of treating it as an alias', () => {
    const original = structuredClone(s3);
    original.tasks[0].concept = 'AssessCommunicationAccuracyTask';
    expect(() => fromContract(original)).toThrow('"AssessCommunicationAccuracyTask" is not a HINT Task concept');
  });
});

describe('S2 reconstruction', () => {
  it('round-trips all entities and explicit relationships without collapsing shared concepts', () => {
    const scenario = fromContract(JSON.stringify(s2));
    expect(validate(scenario)).toEqual([]);
    expect(toContract(scenario)).toEqual(s2);
    expect(scenario.tasks).toHaveLength(10);
    expect(scenario.goal.required_tasks).toEqual(['unlock-cabinet', 'open-cabinet', 'retrieve-tool']);
    expect(scenario.capabilities).toHaveLength(8);
    expect(scenario.capabilities.filter((capability) => capability.tasks.length === 2)).toHaveLength(3);
    expect(scenario.executions.filter((execution) => execution.task === 'heavy-lift')).toHaveLength(2);
    expect(scenario.executions.some((execution) => execution.task === 'retrieve-tool')).toBe(false);
    expect(scenario.experiments.filter((experiment) => experiment.concept === 'SafetyComplianceExperiment').map((experiment) => experiment.id)).toEqual(['reach-safety', 'load-safety']);
    expect(scenario.evaluations.filter((evaluation) => evaluation.concept === 'AIInterventionImpactEvaluation').map((evaluation) => evaluation.id)).toEqual(['reach-safety', 'load-safety']);
    expect(scenario.interactions[0].executions).toEqual([]);
    expect(scenario.experiments.every((experiment) => experiment.hypothesis_language === '')).toBe(true);
  });
});

describe('explicit goal task requirements', () => {
  it('initializes legacy JSON with all tasks selected and exports explicit IDs', () => {
    const scenario = fromContract(JSON.stringify(legacyExample));
    expect(scenario.goal.required_tasks).toEqual(example.goal.required_tasks);
    expect(toContract(scenario)).toEqual(example);
    expect(validate(scenario)).toEqual([]);
    const fresh = emptyScenario();
    expect(fresh.goal.required_tasks).toEqual([fresh.tasks[0].id]);
  });

  it('round-trips an explicit subset independently of capabilities and executions', () => {
    const data = copy();
    data.goal.required_tasks = ['data-collection'];
    const scenario = fromContract(JSON.stringify(data));
    expect(validate(scenario)).toEqual([]);
    expect(toContract(scenario)).toEqual(data);
    expect(scenario.tasks).toHaveLength(3);
    expect(scenario.executions.some((execution) => !scenario.goal.required_tasks.includes(execution.task))).toBe(true);
  });

  it.each([[], null, ['data-collection', 'data-collection'], ['missing'], ['data-collection', 'missing'], 'data-collection', [123], ['task:injected']])('rejects invalid requirement JSON: %j', (references) => {
    expect(() => fromContract({ ...copy(), goal: { ...example.goal, required_tasks: references } })).toThrow('goal.required_tasks');
  });

  it('validates empty, duplicate, and unknown selections and allows repair', () => {
    const scenario = fromContract(copy());
    for (const references of [[], ['data-collection', 'data-collection'], ['missing']]) {
      scenario.goal.required_tasks = references;
      expect(validate(scenario).map((issue) => issue.path)).toContain('goal.required_tasks');
    }
    scenario.goal.required_tasks = ['explanation'];
    expect(validate(scenario)).toEqual([]);
  });

  it('does not select added tasks and removes only references to deleted tasks', () => {
    const scenario = fromContract(legacyExample);
    const task = { ...newTask(), name: 'Supporting task', concept: 'DataCollectionTask' };
    scenario.tasks.push(task);
    expect(scenario.goal.required_tasks).toEqual(example.goal.required_tasks);
    expect(validate(scenario)).toEqual([]);
    removeEntity(scenario, 'tasks', task.id); // Non-required task.
    expect(scenario.goal.required_tasks).toEqual(example.goal.required_tasks);
    scenario.goal.required_tasks = ['data-collection'];
    removeEntity(scenario, 'tasks', 'data-collection');
    expect(scenario.goal.required_tasks).toEqual([]);
    expect(scenario.tasks).toHaveLength(2);
    expect(validate(scenario).map((issue) => issue.path)).toContain('goal.required_tasks');
    expect(toContract(scenario).goal.required_tasks).toEqual([]); // Never fall back to all tasks.
  });

  it('does not extend task records with goal relationship fields', () => {
    const data = copy();
    expect(() => fromContract({ ...data, tasks: [{ ...data.tasks[0], required_tasks: ['data-collection'] }] })).toThrow('required_tasks: unexpected field');
  });
});

describe('optional goal and task descriptions', () => {
  it('round-trips S1 descriptions separately from names and identities', () => {
    const scenario = fromContract(JSON.stringify(example));
    expect(validate(scenario)).toEqual([]);
    expect(toContract(scenario)).toEqual(example);
    scenario.goal.description = ' Updated goal description ';
    scenario.tasks[0].description = ' Updated task description ';
    expect(toContract(scenario).goal).toEqual({ ...example.goal, description: 'Updated goal description' });
    expect(toContract(scenario).tasks[0]).toEqual({ ...example.tasks[0], description: 'Updated task description' });
  });

  it('accepts legacy and null descriptions, and omits cleared form descriptions', () => {
    /** @type {any} */
    const legacy = copy();
    delete legacy.goal.description;
    legacy.tasks.forEach((/** @type {any} */ task) => { delete task.description; });
    const scenario = fromContract(legacy);
    expect(scenario.goal.description).toBe('');
    expect(scenario.tasks.every((task) => task.description === '')).toBe(true);
    expect(toContract(scenario)).toEqual(legacy);
    const nullable = structuredClone(legacy);
    nullable.goal.description = null;
    nullable.tasks.forEach((/** @type {any} */ task) => { task.description = null; });
    expect(toContract(fromContract(nullable))).toEqual(legacy);
    scenario.goal.description = ' \n ';
    scenario.tasks[0].description = ' ';
    expect(validate(scenario)).toEqual([]);
    expect(toContract(scenario)).toEqual(legacy);
    expect(emptyScenario().goal.description).toBe('');
    expect(emptyScenario().tasks[0].description).toBe('');
  });

  it.each(['goal', 'task'])('rejects blank or non-text %s descriptions on import', (kind) => {
    for (const value of ['', ' \n ', 123, false, {}]) {
      /** @type {any} */
      const data = copy();
      const entity = kind === 'goal' ? data.goal : data.tasks[0];
      entity.description = value;
      expect(() => fromContract(data)).toThrow(`${kind === 'goal' ? 'goal' : 'tasks.0'}.description:`);
    }
  });

  it('does not allow descriptions on use cases or agents', () => {
    for (const kind of ['use_case', 'agent']) {
      /** @type {any} */
      const data = copy();
      const entity = kind === 'use_case' ? data.use_case : data.agents[0];
      entity.description = 'Outside this increment';
      expect(() => fromContract(data)).toThrow('description: unexpected field');
    }
  });
});

describe('optional interactions', () => {
  it('keeps legacy JSON compatible and omits empty interaction collections', () => {
    /** @type {any} */
    const data = copy();
    delete data.interactions;
    expect(toContract(fromContract(data))).toEqual(data);
    data.interactions = [];
    expect(toContract(fromContract(data))).not.toHaveProperty('interactions');
    expect(emptyScenario().interactions).toEqual([]);
  });

  it('round-trips three participants, multiple interactions, execution sharing, and descriptions', () => {
    const data = copy();
    data.agents.push({ ...data.agents[0], id: 'third-agent' });
    data.interactions[0].agents.push('third-agent');
    data.interactions[0].executions.push('conflict-resolution');
    const withDescription = { ...data.interactions[0], id: 'another', description: 'English description.' };
    const scenario = fromContract({ ...data, interactions: [data.interactions[0], withDescription] });
    expect(validate(scenario)).toEqual([]);
    expect(toContract(scenario)).toEqual({ ...data, interactions: [data.interactions[0], withDescription] });
    scenario.interactions[0].intent = 'NegotiationIntent';
    expect(toContract(scenario).interactions?.[0].id).toBe(data.interactions[0].id);
    expect(newInteraction(scenario.interactions.map((i) => i.id)).id).toMatch(ID);
  });

  it('accepts interactions without execution links and never derives participants', () => {
    const data = { ...copy(), interactions: [{ id: 'unlinked', intent: 'ExplanationIntent', modality: 'TextChatModality', agents: ['human-user', 'ai-assistant'], description: null }] };
    const scenario = fromContract(data);
    expect(validate(scenario)).toEqual([]);
    expect(toContract(scenario).interactions?.[0]).toMatchObject({ executions: [] });
    expect(toContract(scenario).interactions?.[0]).not.toHaveProperty('description');
    scenario.interactions[0] = { ...newInteraction(), intent: 'ExplanationIntent', modality: 'TextChatModality', executions: ['explanation'] };
    expect(validate(scenario).map((i) => i.path)).toContain('interactions.0.agents');
    expect(scenario.interactions[0].agents).toEqual([]);
  });

  it.each([
    ['intent', 'MadeUpIntent'], ['intent', 'VerbalDialogueModality'],
    ['modality', 'MadeUpModality'], ['modality', 'ExplanationIntent'],
    ['agents', []], ['agents', ['human-user']], ['agents', ['human-user', 'human-user']],
    ['agents', ['human-user', 'ai-assistant', 'human-user']], ['agents', ['human-user', 'missing']],
    ['executions', ['missing']], ['executions', ['explanation', 'explanation']],
    ['description', ' '], ['description', 123],
  ])('rejects invalid interaction field %s', (field, value) => {
    /** @type {any} */
    const data = copy();
    data.interactions[0][field] = value;
    expect(() => fromContract(data)).toThrow();
  });

  it('rejects duplicate interaction IDs and scenario-local intent IRIs', () => {
    const data = copy();
    data.interactions.push({ ...data.interactions[0] });
    expect(() => fromContract(data)).toThrow('Duplicate interaction IDs');
    data.interactions.pop();
    data.interactions[0].intent = 'https://w3id.org/hi-ontology/scenarios/7/IntentGuide';
    expect(() => fromContract(data)).toThrow('not a HINT InteractionIntent concept');
  });

  it.each([null, {}, [{}]])('rejects malformed interaction collections: %j', (interactions) => {
    expect(() => fromContract({ ...copy(), interactions })).toThrow();
  });

  it('preserves interactions when an agent or execution is deleted and requires repair', () => {
    const scenario = fromContract({
      ...copy(), capabilities: [], evaluations: [], experiments: [],
      executions: example.executions.filter((e) => e.agent === 'ai-assistant'),
      agents: [...example.agents, { ...example.agents[0], id: 'replacement-human' }],
    });
    const original = structuredClone(scenario.interactions);
    removeEntity(scenario, 'agents', 'human-user');
    scenario.executions = scenario.executions.filter((e) => e.id !== 'explanation');
    expect(scenario.interactions).toEqual(original);
    expect(validate(scenario).map((i) => i.path)).toEqual(['interactions.0.agents', 'interactions.0.executions']);
    expect(toContract(scenario).interactions?.[0]).toMatchObject(example.interactions[0]);
    scenario.interactions[0].agents = ['ai-assistant', 'replacement-human'];
    scenario.interactions[0].executions = ['conflict-resolution'];
    expect(validate(scenario)).toEqual([]);
    expect(scenario.interactions[0].id).toBe(original[0].id);
  });
});

describe('optional experiments and evaluations', () => {
  it('loads legacy JSON unchanged and omits empty collections on export', () => {
    /** @type {any} */
    const data = copy();
    delete data.experiments;
    delete data.evaluations;
    expect(toContract(fromContract(data))).toEqual(data);
    data.experiments = [];
    data.evaluations = [];
    expect(toContract(fromContract(data))).not.toHaveProperty('experiments');
    expect(toContract(fromContract(data))).not.toHaveProperty('evaluations');
    expect(emptyScenario().experiments).toEqual([]);
    expect(emptyScenario().evaluations).toEqual([]);
  });

  it('round-trips multiple metrics and shared evaluations without merging identities', () => {
    const data = copy();
    data.experiments[0].metrics.push('FairOutcomeMetric');
    data.evaluations[0].metrics.push('FairOutcomeMetric');
    data.evaluations[0].executions = data.executions.map((e) => e.id);
    const scenario = fromContract(JSON.stringify(data));
    expect(validate(scenario)).toEqual([]);
    expect(toContract(scenario)).toEqual(data);
    expect(scenario.experiments.filter((e) => e.concept === 'TransparencyTrustExperiment')).toHaveLength(2);
    scenario.experiments[0].hypothesis_language = 'en';
    scenario.experiments[0].description = ' Experiment description ';
    scenario.evaluations[0].description = '';
    expect(toContract(scenario).experiments?.[0]).toMatchObject({ hypothesis_language: 'en', description: 'Experiment description', id: data.experiments[0].id });
    expect(toContract(scenario).evaluations?.[0]).not.toHaveProperty('description');
    expect(newExperiment(scenario.experiments.map((e) => e.id)).id).toMatch(ID);
    expect(newEvaluation(scenario.evaluations.map((e) => e.id)).id).toMatch(ID);
  });

  it('accepts null optional descriptions and hypothesis language', () => {
    const data = { ...copy(), experiments: [{ ...example.experiments[0], description: null, hypothesis_language: null }] };
    data.evaluations = [data.evaluations[0]];
    expect(toContract(fromContract(data)).experiments?.[0]).toEqual(example.experiments[0]);
  });

  it.each([
    ['experiments', 'id', 'conflict-accuracy'], ['evaluations', 'id', 'conflict-accuracy'],
    ['experiments', 'concept', 'MadeUpExperiment'], ['experiments', 'concept', 'TransparencyEvaluation'],
    ['evaluations', 'concept', 'MadeUpEvaluation'], ['evaluations', 'concept', 'DiagnosisAccuracyMetric'],
    ['experiments', 'metrics', ['MadeUpMetric']], ['evaluations', 'metrics', ['TransparencyEvaluation']],
    ['evaluations', 'experiment', 'missing'], ['evaluations', 'executions', ['missing']],
    ['experiments', 'null_hypothesis', '  '], ['experiments', 'alternative_hypothesis', 123],
    ['experiments', 'hypothesis_language', 'fr'], ['experiments', 'hypothesis_language', ''],
    ['experiments', 'description', ' '], ['evaluations', 'description', 123],
  ])('rejects invalid %s field %s', (collection, field, value) => {
    /** @type {any} */
    const data = copy();
    data[collection][0][field] = value;
    expect(() => fromContract(data)).toThrow();
  });

  it.each([null, {}, [{}]])('rejects malformed assessment collections: %j', (value) => {
    expect(() => fromContract({ ...copy(), experiments: value })).toThrow();
    expect(() => fromContract({ ...copy(), evaluations: value })).toThrow();
  });

  it('preserves evaluations on deletion and requires explicit relationship repair', () => {
    const scenario = fromContract(copy());
    const original = structuredClone(scenario.evaluations);
    scenario.experiments.splice(0, 1);
    scenario.executions.splice(0, 1);
    expect(scenario.evaluations).toEqual(original);
    expect(validate(scenario).map((issue) => issue.path)).toEqual(['evaluations.0.experiment', 'evaluations.0.executions']);
    scenario.evaluations[0].experiment = scenario.experiments[0].id;
    scenario.evaluations[0].executions = [scenario.executions[0].id];
    expect(validate(scenario)).toEqual([]);
    expect(scenario.evaluations[0].id).toBe(original[0].id);
    expect(scenario.evaluations[0].description).toBe(original[0].description);
  });
});

describe('optional task executions', () => {
  it('keeps legacy JSON compatible and omits an empty execution list', () => {
    /** @type {any} */
    const data = copy();
    delete data.interactions;
    delete data.evaluations;
    delete data.experiments;
    delete data.executions;
    expect(toContract(fromContract(data))).toEqual(data);
    data.executions = [];
    expect(toContract(fromContract(data))).not.toHaveProperty('executions');
    expect(emptyScenario().executions).toEqual([]);
  });

  it('round-trips repeated task/agent executions without merging their identities', () => {
    const data = copy();
    data.executions.push({ ...data.executions[0], id: 'repeat' });
    const scenario = fromContract(JSON.stringify(data));
    expect(validate(scenario)).toEqual([]);
    expect(toContract(scenario)).toEqual(data);
    scenario.executions[0].concept = 'ExplanationTaskExecution';
    expect(toContract(scenario).executions?.[0].id).toBe('data-collection');
    expect(newExecution(scenario.executions.map((e) => e.id)).id).toMatch(ID);
  });

  it('accepts absent or null methods and omits unselected methods on export', () => {
    /** @type {any} */
    const data = copy();
    delete data.executions[0].method;
    data.executions[1].method = null;
    const scenario = fromContract(data);
    expect(scenario.executions[0].method).toBe('');
    expect(scenario.executions[1].method).toBe('');
    expect(toContract(scenario).executions?.[0]).not.toHaveProperty('method');
  });

  it.each([
    ['concept', 'MadeUpExecution', 'not a HINT TaskExecution concept'],
    ['concept', 'DataCollectionTask', 'not a HINT TaskExecution concept'],
    ['method', 'MadeUpMethod', 'not a HINT Method concept'],
    ['method', 'DataCollectionTaskExecution', 'not a HINT Method concept'],
    ['agent', 'missing', 'Choose an existing agent'],
    ['task', 'missing', 'Choose an existing task'],
    ['id', 'explanation', 'Duplicate execution IDs'],
  ])('rejects invalid execution %s', (field, value, message) => {
    /** @type {any} */
    const data = copy();
    data.executions[0][field] = value;
    expect(() => fromContract(data)).toThrow(message);
  });

  it.each([
    null, {}, [{}], [{ ...example.executions[0], agent: ['human-user'] }],
    [{ ...example.executions[0], task: null }], [{ ...example.executions[0], method: '' }],
    [{ ...example.executions[0], goal: 'user-wellbeing' }],
  ])('rejects malformed execution JSON: %j', (executions) => {
    expect(() => fromContract({ ...copy(), executions })).toThrow();
  });

  it('preserves execution data after deleting references and requires explicit repair', () => {
    const scenario = fromContract(copy());
    scenario.interactions = []; // Isolate the earlier execution repair contract.
    const original = structuredClone(scenario.executions);
    scenario.agents.push({ ...scenario.agents[0], id: 'replacement-human' });
    removeEntity(scenario, 'agents', 'human-user');
    removeEntity(scenario, 'tasks', 'data-collection');
    expect(scenario.executions).toEqual(original);
    expect(validate(scenario).map((issue) => issue.path)).toEqual(['executions.0.agent', 'executions.0.task']);
    expect(toContract(scenario).executions?.[0]).toMatchObject(example.executions[0]);
    scenario.executions[0].agent = 'replacement-human';
    scenario.executions[0].task = 'explanation';
    expect(validate(scenario)).toEqual([]);
    expect(scenario.executions[0].id).toBe(original[0].id);
    expect(scenario.executions[0].method).toBe(original[0].method);
  });
});

describe('optional capabilities', () => {
  it('loads legacy JSON unchanged and omits an empty capabilities list on export', () => {
    /** @type {any} */
    const data = copy();
    delete data.capabilities;
    expect(toContract(fromContract(data))).toEqual(data);
    data.capabilities = [];
    expect(toContract(fromContract(data))).not.toHaveProperty('capabilities');
    expect(emptyScenario().capabilities).toEqual([]);
  });

  it('round-trips shared capability references without merging equal concepts', () => {
    const data = copy();
    data.capabilities[0].agents = data.agents.map((a) => a.id);
    data.capabilities[0].tasks = data.tasks.map((t) => t.id);
    data.capabilities.push({ ...data.capabilities[0], id: 'another-sensing' });
    const scenario = fromContract(JSON.stringify(data));
    expect(validate(scenario)).toEqual([]);
    expect(toContract(scenario)).toEqual(data);
    scenario.capabilities[0].concept = 'ReasoningCapability';
    scenario.agents[0].name = 'Renamed';
    expect(toContract(scenario).capabilities?.[0].id).toBe('sensing');
    expect(newCapability(scenario.capabilities.map((c) => c.id)).id).toMatch(ID);
  });

  it('allows unassigned capabilities and defaults missing link lists to empty', () => {
    const scenario = fromContract({ ...copy(), capabilities: [{ id: 'unassigned', concept: 'SensingCapability' }] });
    expect(scenario.capabilities).toEqual([{ id: 'unassigned', concept: 'SensingCapability', agents: [], tasks: [] }]);
    expect(validate(scenario)).toEqual([]);
  });

  it.each([
    ['concept', 'MadeUpCapability', 'not a HINT Capability concept'],
    ['concept', 'HumanUserRole', 'not a HINT Capability concept'],
    ['agents', ['missing'], 'Unknown agent ID'],
    ['agents', ['data-collection'], 'Unknown agent ID'],
    ['tasks', ['missing'], 'Unknown task ID'],
    ['tasks', ['ai-assistant'], 'Unknown task ID'],
    ['id', 'self-reporting', 'Duplicate capability IDs'],
  ])('rejects invalid capability %s', (field, value, message) => {
    /** @type {any} */
    const data = copy();
    data.capabilities[0][field] = value;
    expect(() => fromContract(data)).toThrow(message);
  });

  it.each([
    null, {}, [{}], [{ id: 'invalid:id', concept: 'SensingCapability' }],
    [{ id: 'x', concept: 'SensingCapability', agents: null }],
    [{ id: 'x', concept: 'SensingCapability', tasks: 'data-collection' }],
    [{ id: 'x', concept: 'SensingCapability', tasks: [123] }],
    [{ id: 'x', concept: 'SensingCapability', name: 'redundant' }],
  ])('rejects malformed capability JSON: %j', (capabilities) => {
    expect(() => fromContract({ ...copy(), capabilities })).toThrow();
  });

  it('removes only the deleted entity links and keeps capability identities', () => {
    const scenario = fromContract(copy());
    scenario.interactions = [];
    const ids = scenario.capabilities.map((c) => c.id);
    scenario.capabilities[0].agents.push('human-user');
    scenario.capabilities[0].tasks.push('explanation');
    scenario.agents.push({ ...scenario.agents[0], id: 'second-human' });
    removeEntity(scenario, 'agents', 'human-user');
    removeEntity(scenario, 'tasks', 'data-collection');
    expect(validate(scenario).map((issue) => issue.path)).toEqual(['executions.0.agent', 'executions.0.task']);
    expect(scenario.capabilities[0].agents).toEqual(['ai-assistant']);
    expect(scenario.capabilities[0].tasks).toEqual(['explanation']);
    expect(scenario.capabilities[1].agents).toEqual([]);
    expect(scenario.capabilities.map((c) => c.id)).toEqual(ids);
  });
});

describe('optional context', () => {
  it('keeps legacy JSON and null contexts compatible', () => {
    /** @type {any} */
    const data = copy();
    delete data.context;
    expect(toContract(fromContract(data))).toEqual(data);
    data.context = null;
    expect(fromContract(data).context).toBeNull();
    expect(toContract(fromContract(data))).not.toHaveProperty('context');
  });

  it('round-trips every S1 Context field and allows empty concept lists', () => {
    const scenario = fromContract(copy());
    expect(scenario.context).toEqual(example.context);
    expect(toContract(scenario).context).toEqual(example.context);
    scenario.context = { ...newContext(), concept: 'HealthMonitoringContext' };
    expect(validate(scenario)).toEqual([]);
    expect(toContract(scenario).context).toEqual({ concept: 'HealthMonitoringContext', phenomena: [], constraints: [] });
    scenario.context.description = '  Context description  ';
    expect(toContract(scenario).context?.description).toBe('Context description');
  });

  it.each([
    ['concept', 'MadeUpContext'], ['concept', 'HumanUserRole'],
    ['phenomena', ['MadeUpPhenomenon']], ['phenomena', ['PrivacyConstraint']],
    ['constraints', ['MadeUpConstraint']], ['constraints', ['SensorNoisePhenomenon']],
  ])('rejects invalid context vocabulary in %s', (field, value) => {
    /** @type {any} */
    const data = copy();
    data.context[field] = value;
    expect(() => fromContract(data)).toThrow('not a HINT');
  });

  it.each([
    {}, { concept: 'HealthMonitoringContext', phenomena: null },
    { concept: 'HealthMonitoringContext', constraints: 'PrivacyConstraint' },
    { concept: 'HealthMonitoringContext', description: 123 },
    { concept: 'HealthMonitoringContext', description: '  ' },
    { concept: 'HealthMonitoringContext', extra: 'not supported' },
  ])('rejects invalid context structure: %j', (context) => {
    const data = { ...copy(), context };
    expect(() => fromContract(data)).toThrow();
  });
});

describe('example scenario', () => {
  it('loads without issues and round-trips to the identical contract JSON', () => {
    const scenario = fromContract(JSON.stringify(example));
    expect(validate(scenario)).toEqual([]);
    expect(toContract(scenario)).toEqual(example);
  });

  it('omits the optional domain when empty and accepts null', () => {
    /** @type {any} */
    const data = copy();
    data.use_case.domain = null;
    expect(toContract(fromContract(data)).use_case).not.toHaveProperty('domain');
  });
});

describe('generated IDs', () => {
  it('match the model identifier pattern and avoid taken IDs', () => {
    const scenario = emptyScenario();
    const ids = [scenario.id, scenario.use_case.id, scenario.goal.id, ...scenario.tasks.map((t) => t.id), ...scenario.agents.map((a) => a.id)];
    ids.forEach((id) => expect(id).toMatch(ID));
    const taken = Array.from({ length: 200 }, () => newId());
    expect(taken).not.toContain(newId(taken));
  });

  it('do not change when an entity is renamed or re-roled', () => {
    const scenario = fromContract(copy());
    scenario.agents[0].name = 'Renamed';
    scenario.agents[0].roles = ['ClinicianRole'];
    expect(toContract(scenario).agents[0].id).toBe('human-user');
  });
});

describe('validation', () => {
  it('flags every required field of a new scenario', () => {
    const paths = validate(emptyScenario()).map((i) => i.path);
    expect(paths).toEqual(expect.arrayContaining([
      'use_case.name', 'use_case.concept', 'goal.name', 'goal.concept',
      'tasks.0.name', 'tasks.0.concept', 'agents.0.name', 'agents.0.roles',
    ]));
    expect(paths).not.toContain('use_case.domain');
  });

  it('requires both agent kinds and at least two agents', () => {
    const scenario = fromContract(copy());
    scenario.agents[1].kind = 'human';
    expect(validate(scenario).map((i) => i.message)).toContain('The team needs at least one human and one artificial agent.');
    scenario.agents = [newAgent('human')];
    expect(validate(scenario).map((i) => i.message)).toContain('Add at least two agents.');
  });

  it('treats whitespace-only names as missing and trims names in the output', () => {
    const scenario = fromContract(copy());
    scenario.goal.name = '  \n ';
    expect(validate(scenario).map((i) => i.path)).toContain('goal.name');
    scenario.goal.name = '  Wellbeing ';
    expect(toContract(scenario).goal.name).toBe('Wellbeing');
  });
});

describe('loading JSON', () => {
  /** @param {(data: any) => void} mutate */
  const rejects = (mutate) => {
    const data = copy();
    mutate(data);
    return expect(() => fromContract(data));
  };

  it('rejects unknown concepts and concepts from the wrong category', () => {
    rejects((d) => { d.use_case.concept = 'MadeUpUseCase'; }).toThrow('not a HINT UseCase concept');
    rejects((d) => { d.goal.concept = 'DataCollectionTask'; }).toThrow('not a HINT Goal concept');
    rejects((d) => { d.agents[0].roles = ['DataCollectionTask']; }).toThrow('not a HINT Role concept');
    rejects((d) => { d.use_case.concept = 'hint:PersonalAssistantUseCase'; }).toThrow('not a HINT UseCase concept');
  });

  it('rejects structure the Python model forbids', () => {
    rejects((d) => { d.extra_field = 1; }).toThrow('extra_field: unexpected field');
    rejects((d) => { d.use_case.extra_field = 1; }).toThrow('use_case.extra_field: unexpected field');
    rejects((d) => { delete d.goal; }).toThrow('goal: missing');
    rejects((d) => { d.agents[0].kind = 'robot'; }).toThrow('agents.0.kind');
    rejects((d) => { d.agents[0].name = 123; }).toThrow('agents.0.name: expected text');
    rejects((d) => { d.tasks = []; }).toThrow('Add at least one task');
    rejects((d) => { d.agents[1].id = d.agents[0].id; }).toThrow('Duplicate agent IDs');
    rejects((d) => { d.id = 's1\n'; }).toThrow('id: Invalid identifier');
    rejects((d) => { d.id = 's1:agent:injected'; }).toThrow('id: Invalid identifier');
  });

  it('reports invalid JSON text', () => {
    expect(() => fromContract('{ not json')).toThrow('not valid JSON');
    expect(() => fromContract('[]')).toThrow('scenario: expected an object');
  });
});
