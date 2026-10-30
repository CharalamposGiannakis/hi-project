import { describe, expect, it } from 'vitest';
import example from '../../../examples/s1.json';
import { emptyScenario, fromContract, newAgent, newContext, newId, toContract, validate } from './scenario.js';

const ID = /^[a-z0-9][a-z0-9_-]*$/;
const copy = () => structuredClone(example);

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
