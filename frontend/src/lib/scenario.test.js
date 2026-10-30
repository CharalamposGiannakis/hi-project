import { describe, expect, it } from 'vitest';
import example from '../../../examples/s1.json';
import { emptyScenario, fromContract, newAgent, newCapability, newContext, newExecution, newExperiment, newEvaluation, newId, removeEntity, toContract, validate } from './scenario.js';

const ID = /^[a-z0-9][a-z0-9_-]*$/;
const copy = () => structuredClone(example);

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
