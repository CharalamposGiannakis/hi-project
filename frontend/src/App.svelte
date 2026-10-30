<script>
  import example from '../../examples/s1.json';
  import ConceptSelect from './lib/ConceptSelect.svelte';
  import ConceptChecklist from './lib/ConceptChecklist.svelte';
  import ReferenceChecklist from './lib/ReferenceChecklist.svelte';
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
        <label for="goal-name">Description</label>
        <input id="goal-name" bind:value={scenario.goal.name} placeholder="e.g. Maintain and improve user wellbeing" aria-invalid={errorFor('goal.name') ? 'true' : undefined} />
        {#if errorFor('goal.name')}<p class="error">{errorFor('goal.name')}</p>{/if}
      </div>
      <ConceptSelect label="Goal type" category="Goal" bind:value={scenario.goal.concept} error={errorFor('goal.concept')} />
    </fieldset>

    <fieldset>
      <legend>Tasks required by the goal</legend>
      {#if errorFor('tasks')}<p class="error">{errorFor('tasks')}</p>{/if}
      {#each scenario.tasks as task, i (task.id)}
        <section class="item">
          <div class="item-head">
            <h3>Task {i + 1}</h3>
            <button type="button" class="link" onclick={() => removeEntity(scenario, 'tasks', task.id)} disabled={scenario.tasks.length <= 1}>Remove</button>
          </div>
          <div class="field">
            <label for="task-{task.id}">Description</label>
            <input id="task-{task.id}" bind:value={task.name} aria-invalid={errorFor(`tasks.${i}.name`) ? 'true' : undefined} />
            {#if errorFor(`tasks.${i}.name`)}<p class="error">{errorFor(`tasks.${i}.name`)}</p>{/if}
          </div>
          <ConceptSelect label="Task type" category="Task" bind:value={task.concept} error={errorFor(`tasks.${i}.concept`)} />
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
