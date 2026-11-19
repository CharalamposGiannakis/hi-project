<script>
  import { onDestroy, onMount, tick } from 'svelte';
  import { issuePath, requestInterpretation } from './lib/api.js';
  import { createInterpretationDocument, diagnosticLabels, questions, readInterpretationDocument, sampleDescriptions } from './lib/interpretation.js';
  import { createJsonSource } from './lib/json-viewer-channel.js';
  import example from '../../examples/s1.json';
  import EditorSection from './lib/EditorSection.svelte';
  import { vocabularyLabel } from './lib/vocabulary-labels.js';
  import ConceptSelect from './lib/ConceptSelect.svelte';
  import ConceptChecklist from './lib/ConceptChecklist.svelte';
  import ReferenceChecklist from './lib/ReferenceChecklist.svelte';
  import ReferenceSelect from './lib/ReferenceSelect.svelte';
  import RdfPreview from './lib/RdfPreview.svelte';
  import ScenarioWizard from './lib/ScenarioWizard.svelte';
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

  const initialScenario = emptyScenario();
  let scenario = $state(initialScenario);
  let emptyEditor = $state(JSON.stringify(initialScenario));
  let loadedCandidate = $state(false);
  let mode = $state(/** @type {'describe' | 'structured'} */ ('describe'));
  let wizardKey = $state(0);
  let answers = $state(/** @type {import('./lib/interpretation.js').Answers} */ ({}));
  /** @type {import('./lib/interpretation.js').Interpretation} */
  const noInterpretation = { status: 'not_interpreted', diagnostics: [] };
  let interpretation = $state.raw(/** @type {import('./lib/interpretation.js').Interpretation} */ (noInterpretation));
  let generatedBaseline = $state('');
  let pendingInterpretation = $state.raw(/** @type {{ controller: AbortController, target: object } | null} */ (null));
  let interpretationMessage = $state('');
  let interpretationFailed = $state(false);
  let noCandidateAttempt = $state.raw(/** @type {import('./lib/interpretation.js').ModelInterpretation | null} */ (null));
  let showErrors = $state(false);
  let status = $state('');
  let loadError = $state('');
  const sectionIds = ['use_case', 'context', 'team_constraints', 'goal', 'tasks', 'agents', 'capabilities', 'executions', 'experiments', 'evaluations', 'interactions'];
  const compactSections = () => Object.fromEntries(sectionIds.map((id) => [id, id === 'use_case']));
  let expanded = $state(compactSections());
  let revealRequest = $state(0);
  let viewerUrl = $state('');
  let viewerError = $state('');
  // Object identity ties a result to one editor revision, even if edits are later undone.
  let backendFeedback = $state.raw(/** @type {{ target: object, issues: import('./lib/scenario.js').Issue[] } | null} */ (null));

  let issues = $derived(validate(scenario));
  let editorJson = $derived(JSON.stringify(scenario));
  let contract = $derived(toContract(scenario));
  let validationTarget = $derived({ contract, editorJson });
  let candidate = $derived(loadedCandidate || editorJson !== emptyEditor ? contract : null);
  let sourceChanged = $derived(interpretation.source_description
    ? questions.some(({ id }) => answers[id] !== interpretation.source_description?.[id])
    : interpretation.source_changed === true);
  let scenarioChanged = $derived(Boolean(interpretation.generated_scenario && JSON.stringify(candidate) !== generatedBaseline));
  let displayedFindings = $derived(noCandidateAttempt ?? interpretation);
  let draftInterpretation = $derived.by(() => {
    const { source_changed: _source, scenario_changed: _scenario, ...record } = interpretation;
    return { ...record, ...(sourceChanged ? { source_changed: /** @type {const} */ (true) } : {}),
      ...(scenarioChanged ? { scenario_changed: /** @type {const} */ (true) } : {}) };
  });
  let json = $derived(JSON.stringify(createInterpretationDocument(answers, candidate, draftInterpretation), null, 2));
  let visibleIssues = $derived(showErrors ? [...issues, ...(backendFeedback?.target === validationTarget ? backendFeedback.issues : [])] : []);
  let sectionIssues = $derived(Object.fromEntries(sectionIds.map((id) => [id, visibleIssues.filter((issue) => sectionFor(issue.path) === id)])));
  let experimentOptions = $derived(scenario.experiments.map((e) => ({ id: e.id, name: vocabularyLabel('Experiment', findConcept('Experiment', e.concept)?.label ?? 'Experiment') })));
  let executionOptions = $derived(scenario.executions.map((e) => ({
    id: e.id,
    name: `${vocabularyLabel('TaskExecution', findConcept('TaskExecution', e.concept)?.label ?? 'Execution')} · ${scenario.agents.find((a) => a.id === e.agent)?.name || e.agent} · ${scenario.tasks.find((t) => t.id === e.task)?.name || e.task}`,
  })));
  let pristine = JSON.stringify(createInterpretationDocument({}, null, noInterpretation), null, 2);

  const outdatedRequest = 'The draft changed during interpretation. Convert again to use the current draft.';
  $effect(() => {
    if (pendingInterpretation && pendingInterpretation.target !== validationTarget) {
      cancelInterpretation(outdatedRequest);
    }
  });
  onDestroy(() => pendingInterpretation?.controller.abort());

  onMount(() => {
    try {
      const source = createJsonSource(() => json);
      const url = new URL('json-viewer.html', document.baseURI);
      url.hash = source.id;
      viewerUrl = url.href;
      return () => source.close();
    } catch {
      viewerError = 'The separate JSON viewer is unavailable in this browser. Use Copy or Download JSON instead.';
    }
  });

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

  /** @param {import('./lib/api.js').InputIssue[]} errors @param {object} target */
  function revealBackendErrors(errors, target) {
    if (target !== validationTarget) return;
    if (errors.length === 0) {
      backendFeedback = null;
      return;
    }
    backendFeedback = { target, issues: errors.map((issue) => ({
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
    mode = 'structured';
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
      const value = path.split('.').reduce((value, part) => value?.[part], /** @type {any} */ (contract));
      target = controls.find((control) => control instanceof HTMLInputElement && control.value === value) ?? controls[0] ?? field;
    }
    if (target instanceof HTMLElement) {
      target.focus({ preventScroll: true });
      target.scrollIntoView?.({ block: 'nearest' });
    }
  }

  /** @param {string} message */
  function confirmReplace(message) {
    return json === pristine || confirm(message);
  }

  function startNew() {
    if (!confirmReplace('Discard the current scenario and start a new one?')) return;
    loadDraft(null, {}, noInterpretation);
    status = '';
  }

  /**
   * @param {import('./lib/scenario.js').Scenario | null} editor
   * @param {import('./lib/interpretation.js').Answers} sourceAnswers
   * @param {import('./lib/interpretation.js').Interpretation} findings
   */
  function loadDraft(editor, sourceAnswers, findings) {
    const generated = findings.generated_scenario;
    const baseline = generated ? JSON.stringify(toContract(fromContract(generated, { allowDraft: true }))) : '';
    cancelInterpretation();
    scenario = editor ?? emptyScenario();
    emptyEditor = JSON.stringify(scenario);
    loadedCandidate = editor !== null;
    answers = sourceAnswers;
    interpretation = findings;
    generatedBaseline = baseline;
    mode = editor ? 'structured' : 'describe';
    wizardKey += 1;
    showErrors = editor !== null;
    expanded = compactSections();
    backendFeedback = null;
    loadError = '';
    pristine = json;
  }

  /** @param {unknown} data @param {string} source */
  function load(data, source) {
    try {
      const draft = readInterpretationDocument(data);
      if (draft) {
        const editor = draft.scenario === null ? null : fromContract(draft.scenario, { allowDraft: true });
        loadDraft(editor, draft.source_description, draft.interpretation);
      } else {
        loadDraft(fromContract(data), {}, noInterpretation);
      }
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
    if (!file) return;
    try {
      const content = await file.text();
      if (confirmReplace(`Replace the current draft with ${file.name}?`)) load(JSON.parse(content), file.name);
    } catch {
      loadError = `Could not read ${file.name} as JSON.`;
    }
  }

  function markSourceChanged() {
    cancelInterpretation(pendingInterpretation ? outdatedRequest : '');
    if (interpretation.status !== 'not_interpreted' && !interpretation.source_description) {
      interpretation = { ...interpretation, source_changed: true };
    }
  }

  /** @param {import('./lib/interpretation.js').QuestionId} id @param {string} value */
  function answer(id, value) {
    if ((answers[id] ?? '') === value) return;
    if (value) answers[id] = value;
    else delete answers[id];
    markSourceChanged();
  }

  /** @param {'complete' | 'incomplete'} kind */
  function loadDescription(kind) {
    const sample = sampleDescriptions[kind];
    if (JSON.stringify(answers) === JSON.stringify(sample)) return;
    if (Object.values(answers).some((value) => value.length > 0)
        && !confirm('Replace your current description with the sample text?')) return;
    answers = { ...sample };
    markSourceChanged();
  }

  /** @param {string} [message] */
  function cancelInterpretation(message = '') {
    pendingInterpretation?.controller.abort();
    pendingInterpretation = null;
    interpretationMessage = message;
    interpretationFailed = false;
    noCandidateAttempt = null;
  }

  async function interpret() {
    if (pendingInterpretation || !Object.values(answers).some((answer) => answer.trim())) return;
    if (candidate && !confirm('Replace the current structured scenario, including your edits, if AI generates a candidate?')) return;
    const description = { ...answers };
    const request = { controller: new AbortController(), target: validationTarget };
    cancelInterpretation();
    pendingInterpretation = request;
    const result = await requestInterpretation(description, { signal: request.controller.signal });
    if (pendingInterpretation !== request) return;
    if (request.target !== validationTarget) {
      cancelInterpretation(outdatedRequest);
      return;
    }
    pendingInterpretation = null;

    if (result.kind !== 'ok') {
      interpretationFailed = true;
      if (result.kind === 'rejected') {
        const { code, message, issues } = result.error;
        interpretationMessage = code === 'invalid_request'
          ? [message, ...new Set(issues.map((issue) => issue.message))].join('\n')
          : message;
      } else {
        interpretationMessage = result.message;
      }
      return;
    }
    const { scenario: generated, interpretation: findings } = result.data;
    const record = { ...findings, source_description: description, generated_scenario: generated };
    if (generated === null) {
      if (interpretation.generated_scenario) noCandidateAttempt = findings;
      else interpretation = record;
      return;
    }

    let editor;
    try {
      editor = fromContract(generated, { allowDraft: true });
    } catch {
      interpretationFailed = true;
      interpretationMessage = 'The AI returned a candidate that the Structured Editor could not open.';
      return;
    }
    generatedBaseline = JSON.stringify(toContract(editor));
    scenario = editor;
    loadedCandidate = true;
    interpretation = record;
    showErrors = false;
    expanded = compactSections();
    backendFeedback = null;
    status = '';
    if (mode === 'describe') {
      mode = 'structured';
      await tick();
      document.getElementById('structured-mode')?.focus();
    }
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
    download(json, `scenario-${candidate?.id ?? 'description'}-draft.json`);
    pristine = json;
    status = 'JSON downloaded to your computer.';
  }

  function downloadCanonical() {
    download(JSON.stringify(contract, null, 2), `scenario-${scenario.id}.json`);
    status = 'Canonical JSON downloaded to your computer.';
  }

  /** @param {string} content @param {string} filename */
  function download(content, filename) {
    const url = URL.createObjectURL(new Blob([content + '\n'], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  }
</script>

<header>
  <h1>HI Scenario Builder</h1>
  <p class="lead">
    Describe a Hybrid Intelligence scenario, refine its HINT concepts, and validate the resulting RDF.
  </p>
  <div class="toolbar">
    <button type="button" onclick={startNew}>New scenario</button>
    <button type="button" onclick={loadExample}>Load S1 example</button>
    <label class="button file-button">Open JSON file… <input type="file" accept=".json,application/json" onchange={openFile} /></label>
  </div>
  {#if loadError}<pre class="error" role="alert">{loadError}</pre>{/if}
</header>

<main>
  <div class="scenario-editor">
    <div class="toolbar input-methods" role="group" aria-label="Scenario input method">
      <button type="button" aria-controls="description-panel" aria-pressed={mode === 'describe'} onclick={() => (mode = 'describe')}>Describe with AI</button>
      <button type="button" id="structured-mode" aria-controls="structured-panel" aria-pressed={mode === 'structured'} onclick={() => (mode = 'structured')}>Structured Editor</button>
    </div>
    <div id="description-panel" hidden={mode !== 'describe'}>
      {#key wizardKey}
        <ScenarioWizard {answers} onAnswer={answer} onInterpret={interpret} onLoadExample={loadDescription} interpreting={pendingInterpretation !== null} />
      {/key}
    </div>
    <form id="structured-panel" hidden={mode !== 'structured'} onsubmit={(e) => e.preventDefault()} novalidate>
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
            <button type="button" class="link" onclick={() => removeEntity(scenario, 'tasks', task.id)}>Remove</button>
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
            <button type="button" class="link" onclick={() => removeEntity(scenario, 'agents', agent.id)}>Remove</button>
          </div>
          <div class="field">
            <label for="agent-{agent.id}">Name</label>
            <input id="agent-{agent.id}" data-field-path={`agents.${i}.name`} bind:value={agent.name} aria-invalid={errorFor(`agents.${i}.name`) ? 'true' : undefined} aria-describedby={errorFor(`agents.${i}.name`) ? `error-agents.${i}.name` : undefined} />
            {#if errorFor(`agents.${i}.name`)}<p class="error" id={`error-agents.${i}.name`}>{errorFor(`agents.${i}.name`)}</p>{/if}
          </div>
          <div class="field" role="radiogroup" aria-label="Agent kind" data-field-path={`agents.${i}.kind`}
            aria-invalid={errorFor(`agents.${i}.kind`) ? 'true' : undefined}
            aria-describedby={errorFor(`agents.${i}.kind`) ? `error-agents.${i}.kind` : undefined}>
            <span class="label">Kind</span>
            <label class="inline"><input type="radio" bind:group={agent.kind} value="human" /> Human</label>
            <label class="inline"><input type="radio" bind:group={agent.kind} value="artificial" /> Artificial</label>
            {#if errorFor(`agents.${i}.kind`)}<p class="error" id={`error-agents.${i}.kind`}>{errorFor(`agents.${i}.kind`)}</p>{/if}
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
  </div>

  <div class="sidebar">
    <aside aria-label="Scenario validation">
      <RdfPreview target={validationTarget} issueCount={issues.length} onIncomplete={revealErrors} onValidationIssues={revealBackendErrors} />
      {#if visibleIssues.length}
        <ul class="issues" aria-label="Fields needing attention">
          {#each visibleIssues as issue, i (i)}
            <li>
              {#if sectionIds.includes(sectionFor(issue.path))}
                <button type="button" class="link" onclick={() => goToIssue(issue.path)}><code>{issue.path}</code> {issue.message}</button>
              {:else}<code>{issue.path}</code> {issue.message}{/if}
            </li>
          {/each}
        </ul>
      {/if}
      {#if interpretation.status !== 'not_interpreted' || pendingInterpretation || interpretationMessage}
        <section class="interpretation-findings" aria-labelledby="interpretation-heading">
          <h3 id="interpretation-heading">AI interpretation</h3>
          {#if pendingInterpretation && mode === 'structured'}
            <p class="status" role="status">Interpreting description…</p>
          {/if}
          {#if interpretationMessage}
            <p class:error={interpretationFailed} class:hint={!interpretationFailed} role={interpretationFailed ? 'alert' : 'status'}>{interpretationMessage}</p>
          {/if}
          {#if displayedFindings.status !== 'not_interpreted'}
            <p class="hint" role="status">
              {noCandidateAttempt || interpretation.generated_scenario === null ? 'The AI did not return an editable candidate.'
                : displayedFindings.status === 'complete' ? 'The AI generated a candidate. Review it in the Structured Editor.'
                : displayedFindings.status === 'incomplete' ? 'The AI reported issues to review.'
                : 'These findings came from the Phase 1A.1 simulator.'}
            </p>
          {/if}
          {#if !noCandidateAttempt && sourceChanged}
            <p class="warn">The description has changed since interpretation.</p>
          {/if}
          {#if !noCandidateAttempt && scenarioChanged}
            <p class="warn">The structured scenario has changed. These findings describe the generated draft.</p>
          {/if}
          {#if displayedFindings.diagnostics.length}
            <ul class="issues">
              {#each displayedFindings.diagnostics as diagnostic}
                <li>
                  {#if diagnostic.kind}<strong>{diagnosticLabels[diagnostic.kind]}.</strong>{/if}
                  {diagnostic.message}
                  {#if diagnostic.path}<code>{diagnostic.path}</code>{/if}
                </li>
              {/each}
            </ul>
          {/if}
        </section>
      {/if}
    </aside>

    <section class="json-panel" id="json-panel" aria-labelledby="json-heading">
      <div class="item-head">
        <h2 id="json-heading">Scenario JSON</h2>
        {#if viewerUrl}<a class="button" href={viewerUrl} target="_blank" rel="noopener noreferrer">Open JSON in new tab</a>{/if}
      </div>
      {#if viewerError}<p class="error" role="status">{viewerError}</p>{/if}
      <div class="toolbar">
        <button type="button" onclick={copyJson}>Copy</button>
        <button type="button" onclick={downloadJson}>Download JSON</button>
        {#if candidate && issues.length === 0}
          <button type="button" onclick={downloadCanonical}>Download canonical JSON</button>
        {/if}
      </div>
      {#if status}<p class="status" role="status">{status}</p>{/if}
      <!-- svelte-ignore a11y_no_noninteractive_tabindex (Keyboard users need access to the scrollable JSON.) -->
      <pre class="json" id="scenario-json" role="region" tabindex="0" aria-label="Scenario JSON (read-only)">{json}</pre>
    </section>
  </div>
</main>
