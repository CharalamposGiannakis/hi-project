<script>
  import { tick } from 'svelte';
  import { issuePath } from './lib/api.js';
  import example from '../../examples/s1.json';
  import EditorSection from './lib/EditorSection.svelte';
  import { vocabularyLabel } from './lib/vocabulary-labels.js';
  import ConceptSelect from './lib/ConceptSelect.svelte';
  import ConceptChecklist from './lib/ConceptChecklist.svelte';
  import ReferenceChecklist from './lib/ReferenceChecklist.svelte';
  import ReferenceSelect from './lib/ReferenceSelect.svelte';
  import RdfPreview from './lib/RdfPreview.svelte';
  import ScenarioSave from './lib/ScenarioSave.svelte';
  import {
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
  const sectionIds = ['use_case', 'context', 'team_constraints', 'goal', 'tasks', 'agents', 'capabilities', 'executions', 'experiments', 'evaluations', 'interactions'];
  const compactSections = () => Object.fromEntries(sectionIds.map((id) => [id, id === 'use_case']));
  let expanded = $state(compactSections());
  let revealRequest = $state(0);
  let jsonExpanded = $state(false);
  let sidebar = $state(/** @type {HTMLDivElement | undefined} */ (undefined));
  let sidebarScroll = 0;
  // Backend feedback only applies to the exact submitted JSON.
  let backendFeedback = $state(/** @type {{ json: string, issues: import('./lib/scenario.js').Issue[] } | null} */ (null));

  let issues = $derived(validate(scenario));
  let json = $derived(serialize(scenario));
  let visibleIssues = $derived(showErrors ? [...issues, ...(backendFeedback?.json === json ? backendFeedback.issues : [])] : []);
  let attentionIssues = $derived(showErrors ? visibleIssues : issues);
  let sectionIssues = $derived(Object.fromEntries(sectionIds.map((id) => [id, visibleIssues.filter((issue) => sectionFor(issue.path) === id)])));
  let experimentOptions = $derived(scenario.experiments.map((e) => ({ id: e.id, name: vocabularyLabel('Experiment', findConcept('Experiment', e.concept)?.label ?? 'Experiment') })));
  let executionOptions = $derived(scenario.executions.map((e) => ({
    id: e.id,
    name: `${vocabularyLabel('TaskExecution', findConcept('TaskExecution', e.concept)?.label ?? 'Execution')} · ${scenario.agents.find((a) => a.id === e.agent)?.name || e.agent} · ${scenario.tasks.find((t) => t.id === e.task)?.name || e.task}`,
  })));
  // JSON at the last new/load, to ask before discarding edits.
  let pristine = $state(serialize(initial));

  /** @param {import('./lib/scenario.js').Scenario} value */
  function serialize(value) {
    return JSON.stringify(toContract(value), null, 2);
  }

  /** @param {string} path */
  function errorFor(path) {
    // Indexed backend errors describe their checklist without repeating entity errors at the section level.
    return visibleIssues
      .filter((issue) => issue.path === path || (issue.path.startsWith(`${path}.`) && /^\d+$/.test(issue.path.slice(path.length + 1))))
      .map((issue) => issue.message)
      .join(' ');
  }

  /** @param {string} path */
  function sectionFor(path) {
    const root = path.split('.')[0];
    return root === 'id' ? 'use_case' : root;
  }

  function revealErrors() {
    showErrors = true;
    revealRequest += 1;
  }

  /** @param {import('./lib/api.js').InputIssue[]} errors @param {string} sentJson */
  function revealBackendErrors(errors, sentJson) {
    if (sentJson !== json) return;
    if (errors.length === 0) {
      backendFeedback = null;
      return;
    }
    backendFeedback = { json: sentJson, issues: errors.map((issue) => ({
      path: issuePath(issue.location), message: issue.message,
    })) };
    revealErrors();
  }

  /** @param {boolean} open */
  function setAllSections(open) {
    expanded = Object.fromEntries(sectionIds.map((id) => [id, open]));
  }

  /** @param {string} path */
  async function goToIssue(path) {
    const section = sectionFor(path);
    if (!sectionIds.includes(section)) return;
    expanded[section] = true;
    await tick();
    const root = document.getElementById(`section-${section}`);
    const fields = [...(root?.querySelectorAll('[data-field-path]') ?? [])];
    let fieldPath = path;
    let field;
    // Walk up a nested path to its field, entity, then section; never interpolate
    // backend paths into selectors. Entity indexes describe the current form.
    while (fieldPath && !field) {
      field = fields.find((element) => element.getAttribute('data-field-path') === fieldPath);
      if (!field) fieldPath = fieldPath.split('.').slice(0, -1).join('.');
    }
    let target = field ?? root?.querySelector('summary');
    if (field && !field.classList.contains('item')) {
      const controls = [...field.querySelectorAll('input, select, textarea')];
      // For an indexed checklist error, focus the referenced option, not the
      // first checkbox. Unavailable options fall back to the first control or group.
      const value = path.split('.').reduce((value, part) => value?.[part], JSON.parse(json));
      target = controls.find((control) => control instanceof HTMLInputElement && control.value === value) ?? controls[0] ?? field;
    }
    if (target instanceof HTMLElement) {
      target.focus({ preventScroll: true });
      target.scrollIntoView?.({ block: 'nearest' });
    }
  }

  /** @param {MouseEvent} event */
  async function toggleJsonSize(event) {
    const button = /** @type {HTMLButtonElement} */ (event.currentTarget);
    const top = button.getBoundingClientRect().top;
    if (!jsonExpanded) sidebarScroll = sidebar?.scrollTop ?? 0;
    jsonExpanded = !jsonExpanded;
    await tick();
    if (!jsonExpanded && sidebar) sidebar.scrollTop = sidebarScroll;
    // Keep the clicked control in place when the panel changes grid rows.
    const offset = button.getBoundingClientRect().top - top;
    if (offset) window.scrollBy({ top: offset, behavior: 'instant' });
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
    expanded = compactSections();
    backendFeedback = null;
    loadError = '';
    status = '';
  }

  /** @param {unknown} data @param {string} source */
  function load(data, source) {
    try {
      scenario = fromContract(data);
      pristine = serialize(scenario);
      showErrors = true;
      expanded = compactSections();
      backendFeedback = null;
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

  async function copyJson() {
    try {
      await navigator.clipboard.writeText(json);
      status = 'JSON copied to the clipboard.';
    } catch {
      status = 'Copy failed; select the JSON text manually.';
    }
  }

  function downloadJson() {
    revealErrors();
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
    Describe a Hybrid Intelligence scenario using the HINT vocabulary.
  </p>
  <div class="toolbar">
    <button type="button" onclick={startNew}>New scenario</button>
    <button type="button" onclick={loadExample}>Load S1 example</button>
    <label class="button file-button">Open JSON file… <input type="file" accept=".json,application/json" onchange={openFile} /></label>
  </div>
  <p class="notice">
    Previewing stores nothing. Only <strong>Save to GraphDB</strong> stores a scenario, as a new graph that cannot
    be edited or overwritten afterwards. Download the JSON to keep a draft.
  </p>
  {#if loadError}<pre class="error" role="alert">{loadError}</pre>{/if}
</header>

<main class:json-expanded={jsonExpanded}>
  <form onsubmit={(e) => e.preventDefault()} novalidate>
    <div class="toolbar section-controls" aria-label="Editor sections">
      <button type="button" onclick={() => setAllSections(true)}>Expand all</button>
      <button type="button" onclick={() => setAllSections(false)}>Collapse all</button>
    </div>
    <EditorSection id="use_case" title="Use case" bind:open={expanded.use_case} issues={sectionIssues.use_case} {revealRequest}>
      <div class="field">
        <label for="use-case-name">Name</label>
        <input id="use-case-name" data-field-path="use_case.name" bind:value={scenario.use_case.name} placeholder="e.g. Personal assistant HI system" aria-invalid={errorFor('use_case.name') ? 'true' : undefined} aria-describedby={errorFor('use_case.name') ? 'error-use_case.name' : undefined} />
        {#if errorFor('use_case.name')}<p class="error" id="error-use_case.name">{errorFor('use_case.name')}</p>{/if}
      </div>
      <ConceptSelect label="Use case type" category="UseCase" bind:value={scenario.use_case.concept} path="use_case.concept" error={errorFor('use_case.concept')} />
      <ConceptSelect label="Domain" category="Domain" optional bind:value={scenario.use_case.domain} path="use_case.domain" error={errorFor('use_case.domain')} />
    </EditorSection>

    <EditorSection id="context" title="Context" bind:open={expanded.context} issues={sectionIssues.context} {revealRequest} count={scenario.context ? 1 : 0} optional>
      <p class="hint">Describe the conditions in which the team operates.</p>
      {#if scenario.context}
        <ConceptSelect label="Context type" category="Context" bind:value={scenario.context.concept} path="context.concept" error={errorFor('context.concept')} />
        <ConceptChecklist label="Phenomena" category="Phenomenon" bind:values={scenario.context.phenomena} path="context.phenomena" error={errorFor('context.phenomena')} />
        <ConceptChecklist label="Constraints" category="Constraint" bind:values={scenario.context.constraints} path="context.constraints" error={errorFor('context.constraints')} />
        <div class="field">
          <label for="context-description">Description in English (optional)</label>
          <textarea id="context-description" rows="3" data-field-path="context.description" bind:value={scenario.context.description}></textarea>
        </div>
        <button type="button" onclick={() => (scenario.context = null)}>Remove context</button>
      {:else}
        <button type="button" onclick={() => (scenario.context = newContext())}>Add context</button>
      {/if}
    </EditorSection>

    <EditorSection id="team_constraints" title="Team constraints" optional count={scenario.team_constraints.length} bind:open={expanded.team_constraints} issues={sectionIssues.team_constraints} {revealRequest}>
      <ConceptChecklist label="Team constraints (optional)" category="Constraint" bind:values={scenario.team_constraints} path="team_constraints" error={errorFor('team_constraints')} />
    </EditorSection>

    <EditorSection id="goal" title="Team goal" bind:open={expanded.goal} issues={sectionIssues.goal} {revealRequest}>
      <div class="field">
        <label for="goal-name">Name</label>
        <input id="goal-name" data-field-path="goal.name" bind:value={scenario.goal.name} placeholder="e.g. Maintain and improve user wellbeing" aria-invalid={errorFor('goal.name') ? 'true' : undefined} aria-describedby={errorFor('goal.name') ? 'error-goal.name' : undefined} />
        {#if errorFor('goal.name')}<p class="error" id="error-goal.name">{errorFor('goal.name')}</p>{/if}
      </div>
      <ConceptSelect label="Goal type" category="Goal" bind:value={scenario.goal.concept} path="goal.concept" error={errorFor('goal.concept')} />
      <div class="field">
        <label for="goal-description">Description in English (optional)</label>
        <textarea id="goal-description" rows="2" data-field-path="goal.description" bind:value={scenario.goal.description}></textarea>
      </div>
      <ReferenceChecklist label="Tasks required by this goal" options={scenario.tasks} bind:values={scenario.goal.required_tasks} path="goal.required_tasks" error={errorFor('goal.required_tasks')} />
    </EditorSection>

    <EditorSection id="tasks" title="Tasks" bind:open={expanded.tasks} issues={sectionIssues.tasks} {revealRequest} count={scenario.tasks.length}>
      {#if errorFor('tasks')}<p class="error" id="error-tasks">{errorFor('tasks')}</p>{/if}
      {#each scenario.tasks as task, i (task.id)}
        <section class="item" data-field-path={`tasks.${i}`} tabindex="-1">
          <div class="item-head">
            <h3>Task {i + 1}</h3>
            <button type="button" class="link" onclick={() => removeEntity(scenario, 'tasks', task.id)} disabled={scenario.tasks.length <= 1}>Remove</button>
          </div>
          <div class="field">
            <label for="task-{task.id}">Name</label>
            <input id="task-{task.id}" data-field-path={`tasks.${i}.name`} bind:value={task.name} aria-invalid={errorFor(`tasks.${i}.name`) ? 'true' : undefined} aria-describedby={errorFor(`tasks.${i}.name`) ? `error-tasks.${i}.name` : undefined} />
            {#if errorFor(`tasks.${i}.name`)}<p class="error" id={`error-tasks.${i}.name`}>{errorFor(`tasks.${i}.name`)}</p>{/if}
          </div>
          <ConceptSelect label="Task type" category="Task" bind:value={task.concept} path={`tasks.${i}.concept`} error={errorFor(`tasks.${i}.concept`)} />
          <div class="field">
            <label for="task-description-{task.id}">Description in English (optional)</label>
            <textarea id="task-description-{task.id}" rows="2" data-field-path={`tasks.${i}.description`} bind:value={task.description}></textarea>
          </div>
        </section>
      {/each}
      <button type="button" onclick={addTask}>Add task</button>
    </EditorSection>

    <EditorSection id="agents" title="Team members" bind:open={expanded.agents} issues={sectionIssues.agents} {revealRequest} count={scenario.agents.length}>
      {#if errorFor('agents')}<p class="error" id="error-agents">{errorFor('agents')}</p>{/if}
      {#each scenario.agents as agent, i (agent.id)}
        <section class="item" data-field-path={`agents.${i}`} tabindex="-1">
          <div class="item-head">
            <h3>Agent {i + 1}</h3>
            <button type="button" class="link" onclick={() => removeEntity(scenario, 'agents', agent.id)} disabled={scenario.agents.length <= 2}>Remove</button>
          </div>
          <div class="field">
            <label for="agent-{agent.id}">Name</label>
            <input id="agent-{agent.id}" data-field-path={`agents.${i}.name`} bind:value={agent.name} aria-invalid={errorFor(`agents.${i}.name`) ? 'true' : undefined} aria-describedby={errorFor(`agents.${i}.name`) ? `error-agents.${i}.name` : undefined} />
            {#if errorFor(`agents.${i}.name`)}<p class="error" id={`error-agents.${i}.name`}>{errorFor(`agents.${i}.name`)}</p>{/if}
          </div>
          <div class="field" role="radiogroup" aria-label="Agent kind" data-field-path={`agents.${i}.kind`}>
            <span class="label">Kind</span>
            <label class="inline"><input type="radio" bind:group={agent.kind} value="human" /> Human</label>
            <label class="inline"><input type="radio" bind:group={agent.kind} value="artificial" /> Artificial</label>
          </div>
          <ConceptChecklist label="Roles" category="Role" bind:values={agent.roles} path={`agents.${i}.roles`} error={errorFor(`agents.${i}.roles`)} />
        </section>
      {/each}
      <div class="toolbar">
        <button type="button" onclick={() => addAgent('human')}>Add human agent</button>
        <button type="button" onclick={() => addAgent('artificial')}>Add artificial agent</button>
      </div>
    </EditorSection>

    <EditorSection id="capabilities" title="Capabilities" bind:open={expanded.capabilities} issues={sectionIssues.capabilities} {revealRequest} count={scenario.capabilities.length} optional>
      <p class="hint">Define each capability once and link it to agents and tasks. Removing an agent or task removes its links here.</p>
      {#if errorFor('capabilities')}<p class="error" id="error-capabilities">{errorFor('capabilities')}</p>{/if}
      {#each scenario.capabilities as capability, i (capability.id)}
        <section class="item" data-capability-id={capability.id} data-field-path={`capabilities.${i}`} tabindex="-1">
          <div class="item-head">
            <h3>{vocabularyLabel('Capability', findConcept('Capability', capability.concept)?.label ?? '') || `Capability ${i + 1}`}</h3>
            <button type="button" class="link" onclick={() => scenario.capabilities.splice(i, 1)}>Remove capability</button>
          </div>
          <ConceptSelect label="Capability type" category="Capability" bind:value={capability.concept} path={`capabilities.${i}.concept`} error={errorFor(`capabilities.${i}.concept`)} />
          <ReferenceChecklist label="Possessed by agents" options={scenario.agents} bind:values={capability.agents} path={`capabilities.${i}.agents`} error={errorFor(`capabilities.${i}.agents`)} />
          <ReferenceChecklist label="Enables tasks" options={scenario.tasks} bind:values={capability.tasks} path={`capabilities.${i}.tasks`} error={errorFor(`capabilities.${i}.tasks`)} />
        </section>
      {/each}
      <button type="button" onclick={() => scenario.capabilities.push(newCapability(scenario.capabilities.map((c) => c.id)))}>Add capability</button>
    </EditorSection>

    <EditorSection id="executions" title="Task executions" bind:open={expanded.executions} issues={sectionIssues.executions} {revealRequest} count={scenario.executions.length} optional>
      <p class="hint">Describe who performs each task and how, towards the team goal. Deleting an agent or task keeps these records for repair.</p>
      {#if errorFor('executions')}<p class="error" id="error-executions">{errorFor('executions')}</p>{/if}
      {#each scenario.executions as execution, i (execution.id)}
        <section class="item" data-execution-id={execution.id} data-field-path={`executions.${i}`} tabindex="-1">
          <div class="item-head">
            <h3>{vocabularyLabel('TaskExecution', findConcept('TaskExecution', execution.concept)?.label ?? '') || `Execution ${i + 1}`}</h3>
            <button type="button" class="link" onclick={() => scenario.executions.splice(i, 1)}>Remove execution</button>
          </div>
          <ConceptSelect label="Execution type" category="TaskExecution" bind:value={execution.concept} path={`executions.${i}.concept`} error={errorFor(`executions.${i}.concept`)} />
          <ReferenceSelect label="Task" options={scenario.tasks} bind:value={execution.task} path={`executions.${i}.task`} error={errorFor(`executions.${i}.task`)} />
          <ReferenceSelect label="Agent" options={scenario.agents} bind:value={execution.agent} path={`executions.${i}.agent`} error={errorFor(`executions.${i}.agent`)} />
          <ConceptSelect label="Method" category="Method" optional bind:value={execution.method} path={`executions.${i}.method`} error={errorFor(`executions.${i}.method`)} />
        </section>
      {/each}
      <button type="button" onclick={() => scenario.executions.push(newExecution(scenario.executions.map((e) => e.id)))}>Add execution</button>
    </EditorSection>

    <EditorSection id="experiments" title="Experiments" bind:open={expanded.experiments} issues={sectionIssues.experiments} {revealRequest} count={scenario.experiments.length} optional>
      {#if errorFor('experiments')}<p class="error" id="error-experiments">{errorFor('experiments')}</p>{/if}
      {#each scenario.experiments as experiment, i (experiment.id)}
        <section class="item" data-experiment-id={experiment.id} data-field-path={`experiments.${i}`} tabindex="-1">
          <div class="item-head">
            <h3>{vocabularyLabel('Experiment', findConcept('Experiment', experiment.concept)?.label ?? '') || `Experiment ${i + 1}`}</h3>
            <button type="button" class="link" onclick={() => scenario.experiments.splice(i, 1)}>Remove experiment</button>
          </div>
          <ConceptSelect label="Experiment type" category="Experiment" bind:value={experiment.concept} path={`experiments.${i}.concept`} error={errorFor(`experiments.${i}.concept`)} />
          <ConceptChecklist label="Metrics" category="Metric" bind:values={experiment.metrics} path={`experiments.${i}.metrics`} error={errorFor(`experiments.${i}.metrics`)} />
          <div class="field">
            <label for="null-hypothesis-{experiment.id}">Null hypothesis</label>
            <textarea id="null-hypothesis-{experiment.id}" rows="2" data-field-path={`experiments.${i}.null_hypothesis`} bind:value={experiment.null_hypothesis} aria-invalid={errorFor(`experiments.${i}.null_hypothesis`) ? 'true' : undefined} aria-describedby={errorFor(`experiments.${i}.null_hypothesis`) ? `error-experiments.${i}.null_hypothesis` : undefined} ></textarea>
            {#if errorFor(`experiments.${i}.null_hypothesis`)}<p class="error" id={`error-experiments.${i}.null_hypothesis`}>{errorFor(`experiments.${i}.null_hypothesis`)}</p>{/if}
          </div>
          <div class="field">
            <label for="alternative-hypothesis-{experiment.id}">Alternative hypothesis</label>
            <textarea id="alternative-hypothesis-{experiment.id}" rows="2" data-field-path={`experiments.${i}.alternative_hypothesis`} bind:value={experiment.alternative_hypothesis} aria-invalid={errorFor(`experiments.${i}.alternative_hypothesis`) ? 'true' : undefined} aria-describedby={errorFor(`experiments.${i}.alternative_hypothesis`) ? `error-experiments.${i}.alternative_hypothesis` : undefined} ></textarea>
            {#if errorFor(`experiments.${i}.alternative_hypothesis`)}<p class="error" id={`error-experiments.${i}.alternative_hypothesis`}>{errorFor(`experiments.${i}.alternative_hypothesis`)}</p>{/if}
          </div>
          <div class="field">
            <label for="hypothesis-language-{experiment.id}">Hypothesis literal format</label>
            <select id="hypothesis-language-{experiment.id}" data-field-path={`experiments.${i}.hypothesis_language`} bind:value={experiment.hypothesis_language}>
              <option value="">Plain text</option>
              <option value="en">English (@en)</option>
            </select>
          </div>
          <div class="field">
            <label for="experiment-description-{experiment.id}">Description in English (optional)</label>
            <textarea id="experiment-description-{experiment.id}" rows="2" data-field-path={`experiments.${i}.description`} bind:value={experiment.description}></textarea>
          </div>
        </section>
      {/each}
      <button type="button" onclick={() => scenario.experiments.push(newExperiment(scenario.experiments.map((e) => e.id)))}>Add experiment</button>
    </EditorSection>

    <EditorSection id="evaluations" title="Evaluations" bind:open={expanded.evaluations} issues={sectionIssues.evaluations} {revealRequest} count={scenario.evaluations.length} optional>
      <p class="hint">Define each evaluation once and select all executions it evaluates. Deleting an experiment or execution keeps these records for repair.</p>
      {#if errorFor('evaluations')}<p class="error" id="error-evaluations">{errorFor('evaluations')}</p>{/if}
      {#each scenario.evaluations as evaluation, i (evaluation.id)}
        <section class="item" data-evaluation-id={evaluation.id} data-field-path={`evaluations.${i}`} tabindex="-1">
          <div class="item-head">
            <h3>{vocabularyLabel('Evaluation', findConcept('Evaluation', evaluation.concept)?.label ?? '') || `Evaluation ${i + 1}`}</h3>
            <button type="button" class="link" onclick={() => scenario.evaluations.splice(i, 1)}>Remove evaluation</button>
          </div>
          <ConceptSelect label="Evaluation type" category="Evaluation" bind:value={evaluation.concept} path={`evaluations.${i}.concept`} error={errorFor(`evaluations.${i}.concept`)} />
          <ConceptChecklist label="Metrics" category="Metric" bind:values={evaluation.metrics} path={`evaluations.${i}.metrics`} error={errorFor(`evaluations.${i}.metrics`)} />
          <ReferenceSelect label="Experiment" options={experimentOptions} bind:value={evaluation.experiment} path={`evaluations.${i}.experiment`} error={errorFor(`evaluations.${i}.experiment`)} />
          <ReferenceChecklist label="Evaluated executions" options={executionOptions} bind:values={evaluation.executions} path={`evaluations.${i}.executions`} error={errorFor(`evaluations.${i}.executions`)} />
          <div class="field">
            <label for="evaluation-description-{evaluation.id}">Description in English (optional)</label>
            <textarea id="evaluation-description-{evaluation.id}" rows="2" data-field-path={`evaluations.${i}.description`} bind:value={evaluation.description}></textarea>
          </div>
        </section>
      {/each}
      <button type="button" onclick={() => scenario.evaluations.push(newEvaluation(scenario.evaluations.map((e) => e.id)))}>Add evaluation</button>
    </EditorSection>

    <EditorSection id="interactions" title="Interactions" bind:open={expanded.interactions} issues={sectionIssues.interactions} {revealRequest} count={scenario.interactions.length} optional>
      <p class="hint">Select at least two participants explicitly; performers are not added automatically. Related executions are optional. Deleting a referenced record keeps the interaction for repair.</p>
      {#if errorFor('interactions')}<p class="error" id="error-interactions">{errorFor('interactions')}</p>{/if}
      {#each scenario.interactions as interaction, i (interaction.id)}
        <section class="item" data-interaction-id={interaction.id} data-field-path={`interactions.${i}`} tabindex="-1">
          <div class="item-head">
            <h3>{vocabularyLabel('InteractionIntent', findConcept('InteractionIntent', interaction.intent)?.label ?? '') || `Interaction ${i + 1}`}</h3>
            <button type="button" class="link" onclick={() => scenario.interactions.splice(i, 1)}>Remove interaction</button>
          </div>
          <ConceptSelect label="Interaction intent" category="InteractionIntent" bind:value={interaction.intent} path={`interactions.${i}.intent`} error={errorFor(`interactions.${i}.intent`)} />
          <ConceptSelect label="Interaction modality" category="InteractionModality" bind:value={interaction.modality} path={`interactions.${i}.modality`} error={errorFor(`interactions.${i}.modality`)} />
          <ReferenceChecklist label="Participating agents" options={scenario.agents} bind:values={interaction.agents} path={`interactions.${i}.agents`} error={errorFor(`interactions.${i}.agents`)} />
          <ReferenceChecklist label="Related executions (optional)" options={executionOptions} bind:values={interaction.executions} path={`interactions.${i}.executions`} error={errorFor(`interactions.${i}.executions`)} />
          <div class="field">
            <label for="interaction-description-{interaction.id}">Description in English (optional)</label>
            <textarea id="interaction-description-{interaction.id}" rows="2" data-field-path={`interactions.${i}.description`} bind:value={interaction.description}></textarea>
          </div>
        </section>
      {/each}
      <button type="button" onclick={() => scenario.interactions.push(newInteraction(scenario.interactions.map((interaction) => interaction.id)))}>Add interaction</button>
    </EditorSection>
  </form>

  <div class="sidebar" bind:this={sidebar}>
    <aside aria-label="Preview, save, and validation">
      <RdfPreview {json} issueCount={issues.length} onIncomplete={revealErrors} onValidationIssues={revealBackendErrors} />
      <ScenarioSave
        {json}
        issueCount={issues.length}
        onIncomplete={revealErrors}
        onValidationIssues={revealBackendErrors}
        onNewScenarioId={(id) => (scenario.id = id)}
      />
      {#if attentionIssues.length === 0}
        <p class="ok">Form complete (local check).</p>
      {:else}
        <p class="warn">
          Draft — {attentionIssues.length} {attentionIssues.length === 1 ? 'item needs' : 'items need'} attention.
          <button type="button" class="link" onclick={revealErrors}>Show in form</button>
        </p>
        {#if showErrors}
          <ul class="issues">
            {#each visibleIssues as issue, i (i)}
              <li>
                {#if sectionIds.includes(sectionFor(issue.path))}
                  <button type="button" class="link" onclick={() => goToIssue(issue.path)}><code>{issue.path}</code> {issue.message}</button>
                {:else}<code>{issue.path}</code> {issue.message}{/if}
              </li>
            {/each}
          </ul>
        {/if}
      {/if}
    </aside>

    <section class="json-panel" id="json-panel" aria-labelledby="json-heading">
      <div class="item-head">
        <h2 id="json-heading">Scenario JSON</h2>
        <button type="button" aria-expanded={jsonExpanded} aria-controls="scenario-json" onclick={toggleJsonSize}>{jsonExpanded ? 'Restore JSON size' : 'Expand JSON'}</button>
      </div>
      <div class="toolbar">
        <button type="button" onclick={copyJson}>Copy</button>
        <button type="button" onclick={downloadJson}>Download JSON</button>
      </div>
      {#if status}<p class="status" role="status">{status}</p>{/if}
      <!-- svelte-ignore a11y_no_noninteractive_tabindex (Keyboard users need access to the scrollable JSON.) -->
      <pre class="json" id="scenario-json" role="region" tabindex="0" aria-label="Scenario JSON (read-only)">{json}</pre>
      <p class="hint">IDs are generated once and kept when you rename entities; they identify the RDF resources.</p>
    </section>
  </div>
</main>
