// Mirrors hi_scenario/model.py (structure) and hi_scenario/rdf.py (HINT categories).
// The Python model stays authoritative; this gives researchers feedback while editing.
import vocabulary from './hint-vocabulary.json';

/**
 * @typedef {{ id: string, label: string, definition: string }} Concept
 * @typedef {'UseCase' | 'Domain' | 'Goal' | 'Task' | 'Role' | 'Context' | 'Phenomenon' | 'Constraint' | 'Capability' | 'TaskExecution' | 'Method' | 'Experiment' | 'Evaluation' | 'Metric' | 'InteractionIntent' | 'InteractionModality'} Category
 * @typedef {{ id: string, name: string, concept: string }} Entity
 * @typedef {Entity & { description: string }} DescribedEntity
 * @typedef {DescribedEntity & { required_tasks: string[] }} Goal
 * @typedef {Entity & { domain: string }} UseCase  domain is '' when not given
 * @typedef {{ id: string, name: string, kind: 'human' | 'artificial', roles: string[] }} Agent
 * @typedef {{ concept: string, phenomena: string[], constraints: string[], description: string }} Context
 * @typedef {{ id: string, concept: string, agents: string[], tasks: string[] }} Capability
 * @typedef {{ id: string, concept: string, task: string, agent: string, method: string }} Execution
 * @typedef {{ id: string, concept: string, metrics: string[], null_hypothesis: string, alternative_hypothesis: string, hypothesis_language: '' | 'en', description: string }} Experiment
 * @typedef {{ id: string, concept: string, metrics: string[], experiment: string, executions: string[], description: string }} Evaluation
 * @typedef {{ id: string, intent: string, modality: string, agents: string[], executions: string[], description: string }} Interaction
 * @typedef {{ id: string, use_case: UseCase, goal: Goal, tasks: DescribedEntity[], agents: Agent[], team_constraints: string[], context: Context | null, capabilities: Capability[], executions: Execution[], experiments: Experiment[], evaluations: Evaluation[], interactions: Interaction[] }} Scenario
 * @typedef {{ path: string, message: string }} Issue
 */

/** @type {Record<Category, Concept[]>} */
export const concepts = vocabulary;

const ID_PATTERN = /^[a-z0-9][a-z0-9_-]*$/;

/** @type {Record<Category, Map<string, Concept>>} */
const byId = /** @type {any} */ (
  Object.fromEntries(
    Object.entries(concepts).map(([category, list]) => [category, new Map(list.map((c) => [c.id, c]))]),
  )
);

/**
 * @param {Category} category
 * @param {string} id
 */
export function findConcept(category, id) {
  return byId[category].get(id);
}

/**
 * A short random ID, unique among `taken`. IDs are assigned once and never derived
 * from names, so renaming an entity does not change its RDF identity.
 * @param {Iterable<string>} [taken]
 */
export function newId(taken = []) {
  const used = new Set(taken);
  for (;;) {
    const bytes = crypto.getRandomValues(new Uint8Array(4));
    const id = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
    if (!used.has(id)) return id;
  }
}

/** @param {Iterable<string>} [taken] @returns {DescribedEntity} */
export function newTask(taken) {
  return { id: newId(taken), name: '', concept: '', description: '' };
}

/**
 * @param {'human' | 'artificial'} kind
 * @param {Iterable<string>} [taken]
 * @returns {Agent}
 */
export function newAgent(kind, taken) {
  return { id: newId(taken), name: '', kind, roles: [] };
}

/** @returns {Context} */
export function newContext() {
  return { concept: '', phenomena: [], constraints: [], description: '' };
}

/** @param {Iterable<string>} [taken] @returns {Capability} */
export function newCapability(taken) {
  return { id: newId(taken), concept: '', agents: [], tasks: [] };
}

/** @param {Iterable<string>} [taken] @returns {Execution} */
export function newExecution(taken) {
  return { id: newId(taken), concept: '', task: '', agent: '', method: '' };
}

/** @param {Iterable<string>} [taken] @returns {Experiment} */
export function newExperiment(taken) {
  return { id: newId(taken), concept: '', metrics: [], null_hypothesis: '', alternative_hypothesis: '', hypothesis_language: '', description: '' };
}

/** @param {Iterable<string>} [taken] @returns {Evaluation} */
export function newEvaluation(taken) {
  return { id: newId(taken), concept: '', metrics: [], experiment: '', executions: [], description: '' };
}

/** @param {Iterable<string>} [taken] @returns {Interaction} */
export function newInteraction(taken) {
  return { id: newId(taken), intent: '', modality: '', agents: [], executions: [], description: '' };
}

/** Remove an entity and its goal/capability links. Keep executions for explicit repair.
 * @param {Scenario} scenario
 * @param {'agents' | 'tasks'} field
 * @param {string} id
 */
export function removeEntity(scenario, field, id) {
  if (field === 'agents') scenario.agents = scenario.agents.filter((entity) => entity.id !== id);
  else {
    scenario.tasks = scenario.tasks.filter((entity) => entity.id !== id);
    scenario.goal.required_tasks = scenario.goal.required_tasks.filter((reference) => reference !== id);
  }
  for (const capability of scenario.capabilities) {
    capability[field] = capability[field].filter((reference) => reference !== id);
  }
}

/** @returns {Scenario} */
export function emptyScenario() {
  const human = newAgent('human');
  const task = newTask();
  return {
    id: crypto.randomUUID(),
    use_case: { id: newId(), name: '', concept: '', domain: '' },
    goal: { id: newId(), name: '', concept: '', description: '', required_tasks: [task.id] },
    tasks: [task],
    agents: [human, newAgent('artificial', [human.id])],
    team_constraints: [],
    context: null,
    capabilities: [],
    executions: [],
    experiments: [],
    evaluations: [],
    interactions: [],
  };
}

/**
 * Field-level problems that the Python model or RDF mapping would reject.
 * @param {Scenario} scenario
 * @returns {Issue[]}
 */
export function validate(scenario) {
  /** @type {Issue[]} */
  const issues = [];
  /** @param {string} path @param {string} message */
  const add = (path, message) => issues.push({ path, message });
  /** @param {string} path @param {string} id */
  const checkId = (path, id) => {
    if (!ID_PATTERN.test(id)) add(path, 'Invalid identifier.');
  };
  /** @param {string} path @param {string} name */
  const checkName = (path, name) => {
    if (!name.trim()) add(path, 'Enter a name.');
  };
  /** @param {string} path @param {Category} category @param {string} id */
  const checkConcept = (path, category, id) => {
    if (!id) add(path, 'Choose a concept.');
    else if (!findConcept(category, id)) add(path, `"${id}" is not a HINT ${category} concept.`);
  };
  /** @param {string} path @param {{ id: string }[]} entities @param {string} label */
  const checkUnique = (path, entities, label) => {
    const ids = entities.map((e) => e.id);
    if (new Set(ids).size !== ids.length) add(path, `Duplicate ${label} IDs.`);
  };

  checkId('id', scenario.id);
  const { use_case: useCase, goal, tasks, agents } = scenario;
  checkId('use_case.id', useCase.id);
  checkName('use_case.name', useCase.name);
  checkConcept('use_case.concept', 'UseCase', useCase.concept);
  if (useCase.domain) checkConcept('use_case.domain', 'Domain', useCase.domain);
  scenario.team_constraints.forEach((id) => checkConcept('team_constraints', 'Constraint', id));

  if (scenario.context) {
    const context = scenario.context;
    checkConcept('context.concept', 'Context', context.concept);
    context.phenomena.forEach((id) => checkConcept('context.phenomena', 'Phenomenon', id));
    context.constraints.forEach((id) => checkConcept('context.constraints', 'Constraint', id));
  }

  checkId('goal.id', goal.id);
  checkName('goal.name', goal.name);
  checkConcept('goal.concept', 'Goal', goal.concept);
  if (goal.required_tasks.length < 1) add('goal.required_tasks', 'Choose at least one required task.');
  if (new Set(goal.required_tasks).size !== goal.required_tasks.length) add('goal.required_tasks', 'Duplicate required task references.');
  for (const id of goal.required_tasks) {
    if (!tasks.some((task) => task.id === id)) add('goal.required_tasks', `Unknown task ID: ${id}.`);
  }

  if (tasks.length < 1) add('tasks', 'Add at least one task.');
  checkUnique('tasks', tasks, 'task');
  tasks.forEach((task, i) => {
    checkId(`tasks.${i}.id`, task.id);
    checkName(`tasks.${i}.name`, task.name);
    checkConcept(`tasks.${i}.concept`, 'Task', task.concept);
  });

  if (agents.length < 2) add('agents', 'Add at least two agents.');
  checkUnique('agents', agents, 'agent');
  const kinds = new Set(agents.map((a) => a.kind));
  if (!kinds.has('human') || !kinds.has('artificial')) {
    add('agents', 'The team needs at least one human and one artificial agent.');
  }
  agents.forEach((agent, i) => {
    checkId(`agents.${i}.id`, agent.id);
    checkName(`agents.${i}.name`, agent.name);
    if (agent.roles.length < 1) add(`agents.${i}.roles`, 'Choose at least one role.');
    agent.roles.forEach((role) => checkConcept(`agents.${i}.roles`, 'Role', role));
  });
  checkUnique('capabilities', scenario.capabilities, 'capability');
  scenario.capabilities.forEach((capability, i) => {
    const path = `capabilities.${i}`;
    checkId(`${path}.id`, capability.id);
    checkConcept(`${path}.concept`, 'Capability', capability.concept);
    for (const field of /** @type {const} */ (['agents', 'tasks'])) {
      const known = new Set(scenario[field].map((entity) => entity.id));
      for (const id of capability[field]) {
        if (!known.has(id)) add(`${path}.${field}`, `Unknown ${field === 'agents' ? 'agent' : 'task'} ID: ${id}.`);
      }
    }
  });
  checkUnique('executions', scenario.executions, 'execution');
  scenario.executions.forEach((execution, i) => {
    const path = `executions.${i}`;
    checkId(`${path}.id`, execution.id);
    checkConcept(`${path}.concept`, 'TaskExecution', execution.concept);
    if (execution.method) checkConcept(`${path}.method`, 'Method', execution.method);
    if (!agents.some((agent) => agent.id === execution.agent)) add(`${path}.agent`, 'Choose an existing agent.');
    if (!tasks.some((task) => task.id === execution.task)) add(`${path}.task`, 'Choose an existing task.');
  });
  checkUnique('experiments', scenario.experiments, 'experiment');
  scenario.experiments.forEach((experiment, i) => {
    const path = `experiments.${i}`;
    checkId(`${path}.id`, experiment.id);
    checkConcept(`${path}.concept`, 'Experiment', experiment.concept);
    experiment.metrics.forEach((id) => checkConcept(`${path}.metrics`, 'Metric', id));
    if (!experiment.null_hypothesis.trim()) add(`${path}.null_hypothesis`, 'Enter a null hypothesis.');
    if (!experiment.alternative_hypothesis.trim()) add(`${path}.alternative_hypothesis`, 'Enter an alternative hypothesis.');
    if (experiment.hypothesis_language !== '' && experiment.hypothesis_language !== 'en') add(`${path}.hypothesis_language`, 'Choose plain text or English (@en).');
  });
  checkUnique('evaluations', scenario.evaluations, 'evaluation');
  scenario.evaluations.forEach((evaluation, i) => {
    const path = `evaluations.${i}`;
    checkId(`${path}.id`, evaluation.id);
    checkConcept(`${path}.concept`, 'Evaluation', evaluation.concept);
    evaluation.metrics.forEach((id) => checkConcept(`${path}.metrics`, 'Metric', id));
    if (!scenario.experiments.some((experiment) => experiment.id === evaluation.experiment)) add(`${path}.experiment`, 'Choose an existing experiment.');
    evaluation.executions.forEach((id) => {
      if (!scenario.executions.some((execution) => execution.id === id)) add(`${path}.executions`, `Unknown execution ID: ${id}.`);
    });
  });
  checkUnique('interactions', scenario.interactions, 'interaction');
  scenario.interactions.forEach((interaction, i) => {
    const path = `interactions.${i}`;
    checkId(`${path}.id`, interaction.id);
    checkConcept(`${path}.intent`, 'InteractionIntent', interaction.intent);
    checkConcept(`${path}.modality`, 'InteractionModality', interaction.modality);
    if (new Set(interaction.agents).size < 2) add(`${path}.agents`, 'Choose at least two distinct agents.');
    for (const field of /** @type {const} */ (['agents', 'executions'])) {
      const references = interaction[field];
      if (new Set(references).size !== references.length) add(`${path}.${field}`, `Duplicate interaction ${field === 'agents' ? 'agent' : 'execution'} references.`);
      const known = new Set(scenario[field].map((entity) => entity.id));
      for (const id of references) {
        if (!known.has(id)) add(`${path}.${field}`, `Unknown ${field === 'agents' ? 'agent' : 'execution'} ID: ${id}.`);
      }
    }
  });
  return issues;
}

/**
 * The canonical JSON object accepted by `Scenario.model_validate` (names trimmed,
 * optional fields omitted when empty).
 * @param {Scenario} scenario
 */
export function toContract(scenario) {
  const { use_case: useCase, context } = scenario;
  /** @param {Entity} e */
  const entity = (e) => ({ id: e.id, name: e.name.trim(), concept: e.concept });
  /** @param {DescribedEntity} e */
  const describedEntity = (e) => ({ ...entity(e), ...(e.description.trim() ? { description: e.description.trim() } : {}) });
  return {
    id: scenario.id,
    use_case: { ...entity(useCase), ...(useCase.domain ? { domain: useCase.domain } : {}) },
    goal: { ...describedEntity(scenario.goal), required_tasks: [...scenario.goal.required_tasks] },
    tasks: scenario.tasks.map(describedEntity),
    agents: scenario.agents.map((a) => ({ id: a.id, name: a.name.trim(), kind: a.kind, roles: [...a.roles] })),
    ...(scenario.team_constraints.length ? { team_constraints: [...scenario.team_constraints] } : {}),
    ...(scenario.capabilities.length ? { capabilities: scenario.capabilities.map((c) => ({
      id: c.id, concept: c.concept, agents: [...c.agents], tasks: [...c.tasks],
    })) } : {}),
    ...(scenario.executions.length ? { executions: scenario.executions.map((e) => ({
      id: e.id, concept: e.concept, task: e.task, agent: e.agent,
      ...(e.method ? { method: e.method } : {}),
    })) } : {}),
    ...(scenario.experiments.length ? { experiments: scenario.experiments.map((e) => ({
      id: e.id, concept: e.concept, metrics: [...e.metrics],
      null_hypothesis: e.null_hypothesis.trim(), alternative_hypothesis: e.alternative_hypothesis.trim(),
      ...(e.hypothesis_language ? { hypothesis_language: e.hypothesis_language } : {}),
      ...(e.description.trim() ? { description: e.description.trim() } : {}),
    })) } : {}),
    ...(scenario.evaluations.length ? { evaluations: scenario.evaluations.map((e) => ({
      id: e.id, concept: e.concept, metrics: [...e.metrics], experiment: e.experiment, executions: [...e.executions],
      ...(e.description.trim() ? { description: e.description.trim() } : {}),
    })) } : {}),
    ...(scenario.interactions.length ? { interactions: scenario.interactions.map((interaction) => ({
      id: interaction.id, intent: interaction.intent, modality: interaction.modality,
      agents: [...interaction.agents], executions: [...interaction.executions],
      ...(interaction.description.trim() ? { description: interaction.description.trim() } : {}),
    })) } : {}),
    ...(context ? { context: {
      concept: context.concept,
      phenomena: [...context.phenomena],
      constraints: [...context.constraints],
      ...(context.description.trim() ? { description: context.description.trim() } : {}),
    } } : {}),
  };
}

/**
 * Parse contract JSON (text or object) into form state, rejecting anything the
 * Python model would reject. Throws an Error listing the problems.
 * @param {unknown} input
 * @returns {Scenario}
 */
export function fromContract(input) {
  /** @type {string[]} */
  const problems = [];
  let data = input;
  if (typeof input === 'string') {
    try {
      data = JSON.parse(input);
    } catch {
      throw new Error('The file is not valid JSON.');
    }
  }

  // Missing keys are reported once by `object`, so undefined values are skipped below.
  /** @param {string} path @param {string} key */
  const join = (path, key) => (path ? `${path}.${key}` : key);
  /** @param {unknown} value */
  const isObject = (value) => typeof value === 'object' && value !== null && !Array.isArray(value);
  /**
   * @param {unknown} value
   * @param {string} path
   * @param {string[]} required
   * @param {string[]} [optional]
   * @returns {Record<string, any>}
   */
  const object = (value, path, required, optional = []) => {
    if (!isObject(value)) {
      if (value !== undefined) problems.push(`${path || 'scenario'}: expected an object.`);
      return {};
    }
    const record = /** @type {Record<string, any>} */ (value);
    for (const key of required) if (!(key in record)) problems.push(`${join(path, key)}: missing.`);
    for (const key of Object.keys(record)) {
      if (!required.includes(key) && !optional.includes(key)) problems.push(`${join(path, key)}: unexpected field.`);
    }
    return record;
  };
  /** @param {unknown} value @param {string} path */
  const string = (value, path) => {
    if (typeof value !== 'string') {
      if (value !== undefined) problems.push(`${path}: expected text.`);
      return '';
    }
    return value;
  };
  /** @param {unknown} value @param {string} path @returns {unknown[]} */
  const array = (value, path) => {
    if (!Array.isArray(value)) {
      if (value !== undefined) problems.push(`${path}: expected a list.`);
      return [];
    }
    return value;
  };
  /** @param {unknown} value @param {string} path */
  const description = (value, path) => {
    if (value == null) return '';
    const text = string(value, path);
    if (typeof value === 'string' && !text.trim()) problems.push(`${path}: expected nonblank text.`);
    return text;
  };
  /** @param {unknown} value @param {string} path @param {string[]} [optional] @returns {DescribedEntity} */
  const describedEntity = (value, path, optional = []) => {
    const e = object(value, path, ['id', 'name', 'concept'], ['description', ...optional]);
    return {
      id: string(e.id, `${path}.id`), name: string(e.name, `${path}.name`), concept: string(e.concept, `${path}.concept`),
      description: description(e.description, `${path}.description`),
    };
  };

  const root = object(data, '', ['id', 'use_case', 'goal', 'tasks', 'agents'], ['team_constraints', 'context', 'capabilities', 'executions', 'experiments', 'evaluations', 'interactions']);
  const uc = object(root.use_case, 'use_case', ['id', 'name', 'concept'], ['domain']);
  const domain = uc.domain == null ? '' : string(uc.domain, 'use_case.domain');
  /** @type {Context | null} */
  let context = null;
  if (root.context != null) {
    const c = object(root.context, 'context', ['concept'], ['phenomena', 'constraints', 'description']);
    context = {
      concept: string(c.concept, 'context.concept'),
      phenomena: c.phenomena === undefined ? [] : array(c.phenomena, 'context.phenomena').map((id, i) => string(id, `context.phenomena.${i}`)),
      constraints: c.constraints === undefined ? [] : array(c.constraints, 'context.constraints').map((id, i) => string(id, `context.constraints.${i}`)),
      description: c.description == null ? '' : string(c.description, 'context.description'),
    };
    if (typeof c.description === 'string' && !c.description.trim()) problems.push('context.description: expected nonblank text.');
  }
  /** @type {Scenario} */
  const scenario = {
    id: string(root.id, 'id'),
    team_constraints: root.team_constraints === undefined ? [] : array(root.team_constraints, 'team_constraints').map((id, i) => string(id, `team_constraints.${i}`)),
    context,
    interactions: root.interactions === undefined ? [] : array(root.interactions, 'interactions').map((value, i) => {
      const path = `interactions.${i}`;
      const interaction = object(value, path, ['id', 'intent', 'modality', 'agents'], ['executions', 'description']);
      return {
        id: string(interaction.id, `${path}.id`), intent: string(interaction.intent, `${path}.intent`),
        modality: string(interaction.modality, `${path}.modality`),
        agents: array(interaction.agents, `${path}.agents`).map((id, j) => string(id, `${path}.agents.${j}`)),
        executions: interaction.executions === undefined ? [] : array(interaction.executions, `${path}.executions`).map((id, j) => string(id, `${path}.executions.${j}`)),
        description: description(interaction.description, `${path}.description`),
      };
    }),
    experiments: root.experiments === undefined ? [] : array(root.experiments, 'experiments').map((value, i) => {
      const path = `experiments.${i}`;
      const e = object(value, path, ['id', 'concept', 'null_hypothesis', 'alternative_hypothesis'], ['metrics', 'hypothesis_language', 'description']);
      if (e.hypothesis_language != null && e.hypothesis_language !== 'en') problems.push(`${path}.hypothesis_language: choose null or en.`);
      return {
        id: string(e.id, `${path}.id`), concept: string(e.concept, `${path}.concept`),
        metrics: e.metrics === undefined ? [] : array(e.metrics, `${path}.metrics`).map((id, j) => string(id, `${path}.metrics.${j}`)),
        null_hypothesis: string(e.null_hypothesis, `${path}.null_hypothesis`),
        alternative_hypothesis: string(e.alternative_hypothesis, `${path}.alternative_hypothesis`),
        hypothesis_language: e.hypothesis_language === 'en' ? 'en' : '',
        description: description(e.description, `${path}.description`),
      };
    }),
    evaluations: root.evaluations === undefined ? [] : array(root.evaluations, 'evaluations').map((value, i) => {
      const path = `evaluations.${i}`;
      const e = object(value, path, ['id', 'concept', 'experiment'], ['metrics', 'executions', 'description']);
      return {
        id: string(e.id, `${path}.id`), concept: string(e.concept, `${path}.concept`), experiment: string(e.experiment, `${path}.experiment`),
        metrics: e.metrics === undefined ? [] : array(e.metrics, `${path}.metrics`).map((id, j) => string(id, `${path}.metrics.${j}`)),
        executions: e.executions === undefined ? [] : array(e.executions, `${path}.executions`).map((id, j) => string(id, `${path}.executions.${j}`)),
        description: description(e.description, `${path}.description`),
      };
    }),
    executions: root.executions === undefined ? [] : array(root.executions, 'executions').map((value, i) => {
      const path = `executions.${i}`;
      const e = object(value, path, ['id', 'concept', 'task', 'agent'], ['method']);
      if (e.method === '') problems.push(`${path}.method: omit an unspecified method.`);
      return {
        id: string(e.id, `${path}.id`), concept: string(e.concept, `${path}.concept`),
        task: string(e.task, `${path}.task`), agent: string(e.agent, `${path}.agent`),
        method: e.method == null ? '' : string(e.method, `${path}.method`),
      };
    }),
    capabilities: root.capabilities === undefined ? [] : array(root.capabilities, 'capabilities').map((value, i) => {
      const path = `capabilities.${i}`;
      const c = object(value, path, ['id', 'concept'], ['agents', 'tasks']);
      return {
        id: string(c.id, `${path}.id`),
        concept: string(c.concept, `${path}.concept`),
        agents: c.agents === undefined ? [] : array(c.agents, `${path}.agents`).map((id, j) => string(id, `${path}.agents.${j}`)),
        tasks: c.tasks === undefined ? [] : array(c.tasks, `${path}.tasks`).map((id, j) => string(id, `${path}.tasks.${j}`)),
      };
    }),
    use_case: {
      id: string(uc.id, 'use_case.id'),
      name: string(uc.name, 'use_case.name'),
      concept: string(uc.concept, 'use_case.concept'),
      domain,
    },
    goal: { ...describedEntity(root.goal, 'goal', ['required_tasks']), required_tasks: [] },
    tasks: array(root.tasks, 'tasks').map((t, i) => describedEntity(t, `tasks.${i}`)),
    agents: array(root.agents, 'agents').map((value, i) => {
      const path = `agents.${i}`;
      const a = object(value, path, ['id', 'name', 'kind', 'roles']);
      const kind = a.kind === 'human' || a.kind === 'artificial' ? a.kind : 'human';
      if (kind !== a.kind) problems.push(`${path}.kind: must be "human" or "artificial".`);
      const roles = array(a.roles, `${path}.roles`).map((r, j) => string(r, `${path}.roles.${j}`));
      return { id: string(a.id, `${path}.id`), name: string(a.name, `${path}.name`), kind, roles };
    }),
  };

  // Legacy JSON starts with all tasks selected; form state and exports are always explicit.
  scenario.goal.required_tasks = isObject(root.goal) && 'required_tasks' in root.goal
    ? array(root.goal.required_tasks, 'goal.required_tasks').map((id, i) => string(id, `goal.required_tasks.${i}`))
    : scenario.tasks.map((task) => task.id);

  if (problems.length === 0) problems.push(...validate(scenario).map((i) => `${i.path}: ${i.message}`));
  if (problems.length) throw new Error(problems.join('\n'));
  return scenario;
}
