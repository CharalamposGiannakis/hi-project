<script>
  import example from '../../examples/s1.json';
  import ConceptSelect from './lib/ConceptSelect.svelte';
  import ConceptChecklist from './lib/ConceptChecklist.svelte';
  import ReferenceChecklist from './lib/ReferenceChecklist.svelte';
  import ReferenceSelect from './lib/ReferenceSelect.svelte';
  import RdfPreview from './lib/RdfPreview.svelte';
  import ScenarioSave from './lib/ScenarioSave.svelte';
  import {
    concepts,
    emptyScenario,
    findConcept,
    fromContract,
    newAgent,
    newCapability,
    newContext,
    newExecution,
    newExperiment,
    newEvaluation,
    newInteraction,
    newTask,
    removeEntity,
    toContract,
    validate,
  } from './lib/scenario.js';

  const initial = emptyScenario();
  let scenario = $state(initial);
  // Inline errors appear once the researcher asks for a check, not while typing a new form.
  let showErrors = $state(false);
  let status = $state('');
  let loadError = $state('');

  let issues = $derived(validate(scenario));
  let json = $derived(serialize(scenario));
  let experimentOptions = $derived(scenario.experiments.map((e) => ({ id: e.id, name: findConcept('Experiment', e.concept)?.label ?? 'Experiment' })));
  let executionOptions = $derived(scenario.executions.map((e) => ({
    id: e.id,
    name: `${findConcept('TaskExecution', e.concept)?.label ?? 'Execution'} · ${scenario.agents.find((a) => a.id === e.agent)?.name || e.agent} · ${scenario.tasks.find((t) => t.id === e.task)?.name || e.task}`,
  })));
  // JSON at the last new/load, to ask before discarding edits.
  let pristine = $state(serialize(initial));

  /** @param {import('./lib/scenario.js').Scenario} value */
  function serialize(value) {
    return JSON.stringify(toContract(value), null, 2);
  }

  /** @param {string} path */
  function errorFor(path) {
    if (!showErrors) return '';
    return issues
      .filter((issue) => issue.path === path)
      .map((issue) => issue.message)
      .join(' ');
  }

  /** @param {string} message */
  function confirmReplace(message) {
    return json === pristine || confirm(message);
  }

  function startNew() {
    if (!confirmReplace('Discard the current scenario and start a new one?')) return;
    scenario = emptyScenario();
    pristine = serialize(scenario);
    showErrors = false;
    loadError = '';
    status = '';
  }

  /** @param {unknown} data @param {string} source */
  function load(data, source) {
    try {
      scenario = fromContract(data);
      pristine = serialize(scenario);
      showErrors = true;
      loadError = '';
      status = `Loaded ${source}.`;
    } catch (error) {
      loadError = `Could not load ${source}:\n${error instanceof Error ? error.message : error}`;
    }
  }

  function loadExample() {
    if (confirmReplace('Replace the current scenario with the S1 example?')) load(example, 'the S1 example');
  }

  /** @param {Event} event */
  async function openFile(event) {
    const input = /** @type {HTMLInputElement} */ (event.currentTarget);
    const file = input.files?.[0];
    input.value = '';
    if (file && confirmReplace(`Replace the current scenario with ${file.name}?`)) load(await file.text(), file.name);
  }

  function addTask() {
    scenario.tasks.push(newTask(scenario.tasks.map((t) => t.id)));
  }

  /** @param {'human' | 'artificial'} kind */
  function addAgent(kind) {
    scenario.agents.push(newAgent(kind, scenario.agents.map((a) => a.id)));
  }

  /** @param {import('./lib/scenario.js').Agent} agent @param {string} role */
  function toggleRole(agent, role) {
    agent.roles = agent.roles.includes(role) ? agent.roles.filter((r) => r !== role) : [...agent.roles, role];
  }

  async function copyJson() {
    try {
      await navigator.clipboard.writeText(json);
      status = 'JSON copied to the clipboard.';
    } catch {
      status = 'Copy failed; select the JSON text manually.';
    }
  }

  function downloadJson() {
    showErrors = true;
    if (issues.length) {
      status = 'Resolve the listed items before downloading.';
      return;
    }
    const url = URL.createObjectURL(new Blob([json + '\n'], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `scenario-${scenario.id}.json`;
    link.click();
    URL.revokeObjectURL(url);
    pristine = json;
    status = 'JSON downloaded to your computer.';
  }
</script>

<header>
  <h1>HI Scenario Builder</h1>
  <p class="lead">
    Describe one Hybrid Intelligence use case: its goal, the tasks the goal requires, and the human and
    artificial agents in the team. Every choice list comes from the HINT thesaurus.
  </p>
  <div class="toolbar">
    <button type="button" onclick={startNew}>New scenario</button>
    <button type="button" onclick={loadExample}>Load S1 example</button>
    <label class="button">Open JSON file… <input type="file" accept=".json,application/json" onchange={openFile} hidden /></label>
  </div>
  <p class="notice">
    Previewing stores nothing. Only <strong>Save to GraphDB</strong> stores a scenario, as a new graph that cannot
    be edited or overwritten afterwards. Download the JSON to keep a draft.
  </p>
  {#if loadError}<pre class="error" role="alert">{loadError}</pre>{/if}
</header>

<main>
  <form onsubmit={(e) => e.preventDefault()} novalidate>
    <fieldset>
      <legend>Use case</legend>
      <div class="field">
        <label for="use-case-name">Name</label>
        <input id="use-case-name" bind:value={scenario.use_case.name} placeholder="e.g. Personal assistant HI system" aria-invalid={errorFor('use_case.name') ? 'true' : undefined} />
        {#if errorFor('use_case.name')}<p class="error">{errorFor('use_case.name')}</p>{/if}
      </div>
      <ConceptSelect label="Use case type" category="UseCase" bind:value={scenario.use_case.concept} error={errorFor('use_case.concept')} />
      <ConceptSelect label="Domain" category="Domain" optional bind:value={scenario.use_case.domain} error={errorFor('use_case.domain')} />
    </fieldset>

    <fieldset>
      <legend>Context (optional)</legend>
      <p class="hint">Describe the conditions in which the team operates.</p>
      {#if scenario.context}
        <ConceptSelect label="Context type" category="Context" bind:value={scenario.context.concept} error={errorFor('context.concept')} />
        <ConceptChecklist label="Phenomena" category="Phenomenon" bind:values={scenario.context.phenomena} error={errorFor('context.phenomena')} />
        <ConceptChecklist label="Constraints" category="Constraint" bind:values={scenario.context.constraints} error={errorFor('context.constraints')} />
        <div class="field">
          <label for="context-description">Description in English (optional)</label>
          <textarea id="context-description" rows="3" bind:value={scenario.context.description}></textarea>
        </div>
        <button type="button" onclick={() => (scenario.context = null)}>Remove context</button>
      {:else}
        <button type="button" onclick={() => (scenario.context = newContext())}>Add context</button>
      {/if}
    </fieldset>

    <fieldset>
      <legend>Team goal</legend>
      <div class="field">
        <label for="goal-name">Name</label>
        <input id="goal-name" bind:value={scenario.goal.name} placeholder="e.g. Maintain and improve user wellbeing" aria-invalid={errorFor('goal.name') ? 'true' : undefined} />
        {#if errorFor('goal.name')}<p class="error">{errorFor('goal.name')}</p>{/if}
      </div>
      <ConceptSelect label="Goal type" category="Goal" bind:value={scenario.goal.concept} error={errorFor('goal.concept')} />
      <div class="field">
        <label for="goal-description">Description in English (optional)</label>
        <textarea id="goal-description" rows="2" bind:value={scenario.goal.description}></textarea>
      </div>
      <ReferenceChecklist label="Tasks required by this goal" options={scenario.tasks} bind:values={scenario.goal.required_tasks} error={errorFor('goal.required_tasks')} />
    </fieldset>

    <fieldset>
      <legend>Tasks</legend>
      {#if errorFor('tasks')}<p class="error">{errorFor('tasks')}</p>{/if}
      {#each scenario.tasks as task, i (task.id)}
        <section class="item">
          <div class="item-head">
            <h3>Task {i + 1}</h3>
            <button type="button" class="link" onclick={() => removeEntity(scenario, 'tasks', task.id)} disabled={scenario.tasks.length <= 1}>Remove</button>
          </div>
          <div class="field">
            <label for="task-{task.id}">Name</label>
            <input id="task-{task.id}" bind:value={task.name} aria-invalid={errorFor(`tasks.${i}.name`) ? 'true' : undefined} />
            {#if errorFor(`tasks.${i}.name`)}<p class="error">{errorFor(`tasks.${i}.name`)}</p>{/if}
          </div>
          <ConceptSelect label="Task type" category="Task" bind:value={task.concept} error={errorFor(`tasks.${i}.concept`)} />
          <div class="field">
            <label for="task-description-{task.id}">Description in English (optional)</label>
            <textarea id="task-description-{task.id}" rows="2" bind:value={task.description}></textarea>
          </div>
        </section>
      {/each}
      <button type="button" onclick={addTask}>Add task</button>
    </fieldset>

    <fieldset>
      <legend>Team members</legend>
      {#if errorFor('agents')}<p class="error">{errorFor('agents')}</p>{/if}
      {#each scenario.agents as agent, i (agent.id)}
        <section class="item">
          <div class="item-head">
            <h3>Agent {i + 1}</h3>
            <button type="button" class="link" onclick={() => removeEntity(scenario, 'agents', agent.id)} disabled={scenario.agents.length <= 2}>Remove</button>
          </div>
          <div class="field">
            <label for="agent-{agent.id}">Name</label>
            <input id="agent-{agent.id}" bind:value={agent.name} aria-invalid={errorFor(`agents.${i}.name`) ? 'true' : undefined} />
            {#if errorFor(`agents.${i}.name`)}<p class="error">{errorFor(`agents.${i}.name`)}</p>{/if}
          </div>
          <div class="field" role="radiogroup" aria-label="Agent kind">
            <span class="label">Kind</span>
            <label class="inline"><input type="radio" bind:group={agent.kind} value="human" /> Human</label>
            <label class="inline"><input type="radio" bind:group={agent.kind} value="artificial" /> Artificial</label>
          </div>
          <fieldset class="roles">
            <legend>Roles (HINT)</legend>
            {#each concepts.Role as role (role.id)}
              <label class="inline" title={role.definition}>
                <input type="checkbox" checked={agent.roles.includes(role.id)} onchange={() => toggleRole(agent, role.id)} />
                {role.label}
              </label>
            {/each}
            {#each agent.roles as roleId (roleId)}
              {@const role = findConcept('Role', roleId)}
              <p class="hint"><code>hint:{roleId}</code> — {role ? role.definition : 'not a HINT role'}</p>
            {/each}
            {#if errorFor(`agents.${i}.roles`)}<p class="error">{errorFor(`agents.${i}.roles`)}</p>{/if}
          </fieldset>
        </section>
      {/each}
      <div class="toolbar">
        <button type="button" onclick={() => addAgent('human')}>Add human agent</button>
        <button type="button" onclick={() => addAgent('artificial')}>Add artificial agent</button>
      </div>
    </fieldset>

    <fieldset>
      <legend>Capabilities (optional)</legend>
      <p class="hint">Define each capability once and link it to agents and tasks. Removing an agent or task removes its links here.</p>
      {#if errorFor('capabilities')}<p class="error">{errorFor('capabilities')}</p>{/if}
      {#each scenario.capabilities as capability, i (capability.id)}
        <section class="item" data-capability-id={capability.id}>
          <div class="item-head">
            <h3>{findConcept('Capability', capability.concept)?.label ?? `Capability ${i + 1}`}</h3>
            <button type="button" class="link" onclick={() => scenario.capabilities.splice(i, 1)}>Remove capability</button>
          </div>
          <ConceptSelect label="Capability type" category="Capability" bind:value={capability.concept} error={errorFor(`capabilities.${i}.concept`)} />
          <ReferenceChecklist label="Possessed by agents" options={scenario.agents} bind:values={capability.agents} error={errorFor(`capabilities.${i}.agents`)} />
          <ReferenceChecklist label="Enables tasks" options={scenario.tasks} bind:values={capability.tasks} error={errorFor(`capabilities.${i}.tasks`)} />
        </section>
      {/each}
      <button type="button" onclick={() => scenario.capabilities.push(newCapability(scenario.capabilities.map((c) => c.id)))}>Add capability</button>
    </fieldset>

    <fieldset>
      <legend>Task executions (optional)</legend>
      <p class="hint">Describe who performs each task and how, towards the team goal. Deleting an agent or task keeps these records for repair.</p>
      {#if errorFor('executions')}<p class="error">{errorFor('executions')}</p>{/if}
      {#each scenario.executions as execution, i (execution.id)}
        <section class="item" data-execution-id={execution.id}>
          <div class="item-head">
            <h3>{findConcept('TaskExecution', execution.concept)?.label ?? `Execution ${i + 1}`}</h3>
            <button type="button" class="link" onclick={() => scenario.executions.splice(i, 1)}>Remove execution</button>
          </div>
          <ConceptSelect label="Execution type" category="TaskExecution" bind:value={execution.concept} error={errorFor(`executions.${i}.concept`)} />
          <ReferenceSelect label="Task" options={scenario.tasks} bind:value={execution.task} error={errorFor(`executions.${i}.task`)} />
          <ReferenceSelect label="Agent" options={scenario.agents} bind:value={execution.agent} error={errorFor(`executions.${i}.agent`)} />
          <ConceptSelect label="Method" category="Method" optional bind:value={execution.method} error={errorFor(`executions.${i}.method`)} />
        </section>
      {/each}
      <button type="button" onclick={() => scenario.executions.push(newExecution(scenario.executions.map((e) => e.id)))}>Add execution</button>
    </fieldset>

    <fieldset>
      <legend>Experiments (optional)</legend>
      {#if errorFor('experiments')}<p class="error">{errorFor('experiments')}</p>{/if}
      {#each scenario.experiments as experiment, i (experiment.id)}
        <section class="item" data-experiment-id={experiment.id}>
          <div class="item-head">
            <h3>{findConcept('Experiment', experiment.concept)?.label ?? `Experiment ${i + 1}`}</h3>
            <button type="button" class="link" onclick={() => scenario.experiments.splice(i, 1)}>Remove experiment</button>
          </div>
          <ConceptSelect label="Experiment type" category="Experiment" bind:value={experiment.concept} error={errorFor(`experiments.${i}.concept`)} />
          <ConceptChecklist label="Metrics" category="Metric" bind:values={experiment.metrics} error={errorFor(`experiments.${i}.metrics`)} />
          <div class="field">
            <label for="null-hypothesis-{experiment.id}">Null hypothesis</label>
            <textarea id="null-hypothesis-{experiment.id}" rows="2" bind:value={experiment.null_hypothesis} aria-invalid={errorFor(`experiments.${i}.null_hypothesis`) ? 'true' : undefined}></textarea>
            {#if errorFor(`experiments.${i}.null_hypothesis`)}<p class="error">{errorFor(`experiments.${i}.null_hypothesis`)}</p>{/if}
          </div>
          <div class="field">
            <label for="alternative-hypothesis-{experiment.id}">Alternative hypothesis</label>
            <textarea id="alternative-hypothesis-{experiment.id}" rows="2" bind:value={experiment.alternative_hypothesis} aria-invalid={errorFor(`experiments.${i}.alternative_hypothesis`) ? 'true' : undefined}></textarea>
            {#if errorFor(`experiments.${i}.alternative_hypothesis`)}<p class="error">{errorFor(`experiments.${i}.alternative_hypothesis`)}</p>{/if}
          </div>
          <div class="field">
            <label for="hypothesis-language-{experiment.id}">Hypothesis literal format</label>
            <select id="hypothesis-language-{experiment.id}" bind:value={experiment.hypothesis_language}>
              <option value="">Plain text</option>
              <option value="en">English (@en)</option>
            </select>
          </div>
          <div class="field">
            <label for="experiment-description-{experiment.id}">Description in English (optional)</label>
            <textarea id="experiment-description-{experiment.id}" rows="2" bind:value={experiment.description}></textarea>
          </div>
        </section>
      {/each}
      <button type="button" onclick={() => scenario.experiments.push(newExperiment(scenario.experiments.map((e) => e.id)))}>Add experiment</button>
    </fieldset>

    <fieldset>
      <legend>Evaluations (optional)</legend>
      <p class="hint">Define each evaluation once and select all executions it evaluates. Deleting an experiment or execution keeps these records for repair.</p>
      {#if errorFor('evaluations')}<p class="error">{errorFor('evaluations')}</p>{/if}
      {#each scenario.evaluations as evaluation, i (evaluation.id)}
        <section class="item" data-evaluation-id={evaluation.id}>
          <div class="item-head">
            <h3>{findConcept('Evaluation', evaluation.concept)?.label ?? `Evaluation ${i + 1}`}</h3>
            <button type="button" class="link" onclick={() => scenario.evaluations.splice(i, 1)}>Remove evaluation</button>
          </div>
          <ConceptSelect label="Evaluation type" category="Evaluation" bind:value={evaluation.concept} error={errorFor(`evaluations.${i}.concept`)} />
          <ConceptChecklist label="Metrics" category="Metric" bind:values={evaluation.metrics} error={errorFor(`evaluations.${i}.metrics`)} />
          <ReferenceSelect label="Experiment" options={experimentOptions} bind:value={evaluation.experiment} error={errorFor(`evaluations.${i}.experiment`)} />
          <ReferenceChecklist label="Evaluated executions" options={executionOptions} bind:values={evaluation.executions} error={errorFor(`evaluations.${i}.executions`)} />
          <div class="field">
            <label for="evaluation-description-{evaluation.id}">Description in English (optional)</label>
            <textarea id="evaluation-description-{evaluation.id}" rows="2" bind:value={evaluation.description}></textarea>
          </div>
        </section>
      {/each}
      <button type="button" onclick={() => scenario.evaluations.push(newEvaluation(scenario.evaluations.map((e) => e.id)))}>Add evaluation</button>
    </fieldset>

    <fieldset>
      <legend>Interactions (optional)</legend>
      <p class="hint">Select at least two participants explicitly; performers are not added automatically. Related executions are optional. Deleting a referenced record keeps the interaction for repair.</p>
      {#if errorFor('interactions')}<p class="error">{errorFor('interactions')}</p>{/if}
      {#each scenario.interactions as interaction, i (interaction.id)}
        <section class="item" data-interaction-id={interaction.id}>
          <div class="item-head">
            <h3>{findConcept('InteractionIntent', interaction.intent)?.label ?? `Interaction ${i + 1}`}</h3>
            <button type="button" class="link" onclick={() => scenario.interactions.splice(i, 1)}>Remove interaction</button>
          </div>
          <ConceptSelect label="Interaction intent" category="InteractionIntent" bind:value={interaction.intent} error={errorFor(`interactions.${i}.intent`)} />
          <ConceptSelect label="Interaction modality" category="InteractionModality" bind:value={interaction.modality} error={errorFor(`interactions.${i}.modality`)} />
          <ReferenceChecklist label="Participating agents" options={scenario.agents} bind:values={interaction.agents} error={errorFor(`interactions.${i}.agents`)} />
          <ReferenceChecklist label="Related executions (optional)" options={executionOptions} bind:values={interaction.executions} error={errorFor(`interactions.${i}.executions`)} />
          <div class="field">
            <label for="interaction-description-{interaction.id}">Description in English (optional)</label>
            <textarea id="interaction-description-{interaction.id}" rows="2" bind:value={interaction.description}></textarea>
          </div>
        </section>
      {/each}
      <button type="button" onclick={() => scenario.interactions.push(newInteraction(scenario.interactions.map((interaction) => interaction.id)))}>Add interaction</button>
    </fieldset>
  </form>

  <aside>
    <RdfPreview {json} issueCount={issues.length} onIncomplete={() => (showErrors = true)} />
    <ScenarioSave
      {json}
      issueCount={issues.length}
      onIncomplete={() => (showErrors = true)}
      onNewScenarioId={(id) => (scenario.id = id)}
    />

    <h2>Scenario JSON</h2>
    {#if issues.length === 0}
      <p class="ok">Form complete (local check).</p>
    {:else}
      <p class="warn">
        Draft — {issues.length} {issues.length === 1 ? 'item needs' : 'items need'} attention.
        <button type="button" class="link" onclick={() => (showErrors = true)}>Show in form</button>
      </p>
      {#if showErrors}
        <ul class="issues">
          {#each issues as issue, i (i)}<li><code>{issue.path}</code> {issue.message}</li>{/each}
        </ul>
      {/if}
    {/if}
    <div class="toolbar">
      <button type="button" onclick={copyJson}>Copy</button>
      <button type="button" onclick={downloadJson}>Download JSON</button>
    </div>
    {#if status}<p class="status" role="status">{status}</p>{/if}
    <pre class="json">{json}</pre>
    <p class="hint">IDs are generated once and kept when you rename entities; they identify the RDF resources.</p>
  </aside>
</main>
