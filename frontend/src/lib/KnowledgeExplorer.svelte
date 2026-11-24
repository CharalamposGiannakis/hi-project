<script>
  import { onDestroy } from 'svelte';
  import { fetchExplorerCatalog, requestExplorerQuery } from './api.js';
  import { concepts } from './scenario.js';
  import { vocabularyLabel } from './vocabulary-labels.js';
  import CrossScenarioExplorer from './CrossScenarioExplorer.svelte';
  import ScenarioUploads from './ScenarioUploads.svelte';

  /** @typedef {import('./api.js').ExplorerQuestionId} QuestionId */
  /** @typedef {import('./api.js').ExplorerScope} Scope */
  /** @typedef {import('./api.js').ExplorerRequest} Query */
  /** @typedef {ReturnType<typeof import('./scenario.js').toContract>} Draft */
  /** @typedef {Awaited<ReturnType<typeof requestExplorerQuery>>} Outcome */
  /** @type {{ active: boolean, draft: Draft | null }} */
  let { active, draft } = $props();

  // Draft queries are useful even when GraphDB cannot provide the shared catalog.
  const originalQuestions = {
    cq1: "Given a use case, how is the hybrid intelligence team composed, and what roles do its agents assume?",
    cq2: "Given an agent's capabilities, which tasks can it perform, and in which use cases can it participate?",
    cq3: "What candidate team compositions satisfy all capability requirements for achieving a specific goal?",
    cq4: "How can we infer team eligibility, task assignment, or contextual influences?",
    cq5: "What types of interactions occur between agents during the execution of a specific task?",
    cq6: "Given a method, which goals and tasks can be achieved with it?",
    cq7: "Given an evaluation metric, which task can be assessed with it?",
    cq8: "Given a goal, which experiments test which metrics, and what hypotheses do these experiments address?",
    cq9: "Given a contextual constraint, which use cases are associated with it, and how does it affect the team?",
    cq10: "Which constraints are shared across different use cases and agents?",
    cq11: "Given a use case, which contextual phenomena are associated with it?",
    cq12: "Under what conditions does an agent's behaviour comply with or violate a contextual constraint associated with a use case?",
  };
  const pendingIds = ['cq3', 'cq4', 'cq12'];
  const pendingReason = 'Reliable answers require further scientific clarification or ontology development.';
  const fallbackQuestions = /** @type {import('./api.js').ExplorerQuestion[]} */ ([
    { id: 'cq1', label: 'CQ1 · Team members and roles', description: '', parameters: [] },
    { id: 'cq2', label: 'CQ2 · Tasks supported by capabilities', description: 'Which tasks have their recorded capability requirements covered by members of the same HI team? Coverage is derived from capabilities and does not establish task execution.', parameters: [] },
    { id: 'cq5', label: 'CQ5 · Interactions during task execution', description: 'CQ5 requires recorded links between interactions and executions of goal-required tasks.', parameters: [] },
    { id: 'cq8', label: 'CQ8 · Experiments, metrics, and hypotheses', description: 'Which experiments and metrics are linked through executions that contribute to the goal or realize its required tasks?', parameters: [] },
    { id: 'cq11', label: 'CQ11 · Contextual phenomena', description: '', parameters: [] },
    { id: 'cq3', label: 'CQ3 · Candidate team compositions', description: '', parameters: [] },
    { id: 'cq4', label: 'CQ4 · Inferred relationships', description: '', parameters: [] },
    { id: 'cq6', label: 'CQ6 · Methods, goals, and tasks', description: 'Recorded method executions associate goals and tasks.', parameters: [{ id: 'method', label: 'Method', category: 'Method' }] },
    { id: 'cq7', label: 'CQ7 · Metrics and assessed tasks', description: 'Tasks linked to recorded metric evaluations.', parameters: [{ id: 'metric', label: 'Metric', category: 'Metric' }] },
    { id: 'cq9', label: 'CQ9 · Contextual constraints', description: 'Context constraints and recorded influence relationships.', parameters: [{ id: 'constraint', label: 'Constraint', category: 'Constraint' }] },
    { id: 'cq10', label: 'CQ10 · Shared constraints', description: 'Constraints recorded across at least two distinct use cases.', parameters: [] },
    { id: 'cq12', label: 'CQ12 · Compliance with contextual constraints', description: '', parameters: [] },
  ]).sort((first, second) => Number(first.id.slice(2)) - Number(second.id.slice(2)));
  const statuses = { approved: 'Approved', reference: 'Experimental reference', provisional: 'Provisional draft' };

  /** @param {import('./api.js').ExplorerSource} source */
  const sourceStatus = (source) => source.publication_status === 'provisional' && source.file_name
    ? 'Provisional upload' : statuses[source.publication_status];

  let scope = $state(/** @type {Scope} */ ('draft'));
  let mode = $state(/** @type {'questions' | 'find' | 'compare'} */ ('questions'));
  let questionId = $state(/** @type {QuestionId} */ ('cq1'));
  let sharedScenarioId = $state('');
  let includeCurrent = $state(true);
  let uploads = $state(/** @type {import('./api.js').SessionUpload[]} */ ([]));
  let selectedUploads = $derived(uploads.filter((upload) => upload.selected).map(({ selected: _selected, ...upload }) => upload));
  let parameters = $state(/** @type {Record<string, string>} */ ({}));
  let catalog = $state.raw(/** @type {Awaited<ReturnType<typeof fetchExplorerCatalog>> | null} */ (null));
  let loadingCatalog = $state(false);
  const catalogController = new AbortController();
  let pending = $state.raw(/** @type {{ query: Query, controller: AbortController } | null} */ (null));
  let result = $state.raw(/** @type {{ query: Query, outcome: Outcome } | null} */ (null));

  let shared = $derived(catalog?.kind === 'ok' ? catalog.data : null);
  let sharedLabel = $derived(shared?.shared_source === 'approved' ? 'Approved scenarios'
    : shared?.shared_source === 'reference' ? 'Experimental reference scenarios' : 'Shared scenarios');
  let questions = $derived(shared?.questions.length ? shared.questions : fallbackQuestions);
  let question = $derived(questions.find(({ id }) => id === questionId) ?? questions[0]);
  let scientificPending = $derived(question.status === 'scientific_review_pending' || pendingIds.includes(question.id));
  let selectedScenario = $derived(shared?.scenarios.find((source) => source.scenario_id === sharedScenarioId));
  let includesDraft = $derived(scope !== 'shared');
  let includesShared = $derived(scope !== 'draft');
  let query = $derived(/** @type {Query} */ ({
    question_id: questionId, scope,
    ...(includesDraft && includeCurrent && draft ? { scenario: draft } : {}),
    ...(includesDraft && selectedUploads.length ? { uploads: selectedUploads } : {}),
    ...(includesShared && selectedScenario ? { shared_scenario_id: selectedScenario.scenario_id } : {}),
    ...(Object.keys(parameters).length ? { parameters: { ...parameters } } : {}),
  }));
  let canRun = $derived(!scientificPending && (!includesDraft || (includeCurrent && draft !== null) || selectedUploads.length > 0)
    && (!includesShared || Boolean(shared?.scenarios.length)));
  let outcome = $derived(result?.query === query ? result.outcome : null);

  $effect(() => {
    if (active && !catalog && !loadingCatalog) void loadCatalog();
  });
  $effect(() => {
    if (pending && pending.query !== query) {
      pending.controller.abort();
      pending = null;
    }
  });
  onDestroy(() => {
    catalogController.abort();
    pending?.controller.abort();
  });

  async function loadCatalog() {
    loadingCatalog = true;
    catalog = await fetchExplorerCatalog({ signal: catalogController.signal });
    loadingCatalog = false;
    if (catalog.kind === 'ok' && !catalog.data.scenarios.some((source) => source.scenario_id === sharedScenarioId)) {
      sharedScenarioId = '';
    }
  }

  /** @param {Event} event */
  function chooseQuestion(event) {
    if (!(event.currentTarget instanceof HTMLSelectElement)) return;
    const value = event.currentTarget.value;
    const selected = questions.find(({ id }) => id === value);
    if (!selected) return;
    questionId = selected.id;
    parameters = {};
  }

  /** @param {string} id @param {string} value */
  function chooseParameter(id, value) {
    if (value) parameters[id] = value;
    else delete parameters[id];
  }

  async function run() {
    if (!canRun || pending) return;
    const submitted = query;
    const controller = new AbortController();
    pending = { query: submitted, controller };
    result = null;
    const response = await requestExplorerQuery(submitted, { signal: controller.signal });
    if (pending?.controller !== controller) return;
    pending = null;
    if (submitted === query) result = { query: submitted, outcome: response };
  }
</script>

<ScenarioUploads bind:uploads />

<nav class="toolbar" aria-label="Knowledge Explorer tools">
  <button type="button" aria-pressed={mode === 'questions'} onclick={() => (mode = 'questions')}>Competency questions</button>
  <button type="button" aria-pressed={mode === 'find'} onclick={() => (mode = 'find')}>Find concepts</button>
  <button type="button" aria-pressed={mode === 'compare'} onclick={() => (mode = 'compare')}>Compare scenarios</button>
</nav>

<div hidden={mode !== 'questions'}>
<section class="explorer-panel" aria-labelledby="explorer-controls-heading">
  <h2 id="explorer-controls-heading">Query scenarios</h2>
  <form onsubmit={(event) => { event.preventDefault(); void run(); }}>
    <fieldset class="source-options">
      <legend>Query source</legend>
      <label class="inline"><input type="radio" id="explorer-source-draft" bind:group={scope} value="draft" /> My current scenario and selected uploads</label>
      <label class="inline"><input type="radio" id="explorer-source-approved" bind:group={scope} value="shared" /> {sharedLabel}</label>
      <label class="inline"><input type="radio" id="explorer-source-combined" bind:group={scope} value="combined" /> My current scenario, selected uploads, and {sharedLabel.toLowerCase()}</label>
    </fieldset>

    {#if includesDraft}
      <label class="inline"><input id="explorer-include-current" type="checkbox" bind:checked={includeCurrent} /> Include current Builder scenario</label>
      <p class="hint">{draft ? `${draft.use_case.name || 'Untitled scenario'} · Provisional draft` : 'Start or open a structured scenario in the Scenario Builder to query your draft.'}</p>
      {#if selectedUploads.length}<p class="hint">{selectedUploads.length} selected provisional uploads will participate.</p>{/if}
    {/if}

    {#each shared?.warnings ?? [] as warning}
      <p class="hint" role="status">{warning}</p>
    {/each}

    {#if loadingCatalog}
      <p class="status" role="status">Loading shared scenarios…</p>
    {:else if catalog && catalog.kind !== 'ok'}
      <p class="error" role="alert">Shared scenarios could not be loaded.</p>
      <button class="link" type="button" onclick={loadCatalog}>Retry loading shared scenarios</button>
    {:else if includesShared && shared}
      {#if shared.scenarios.length}
        <div class="field">
          <label for="explorer-scenario">Scenario</label>
          <select id="explorer-scenario" bind:value={sharedScenarioId}>
            <option value="">All {sharedLabel.toLowerCase()}</option>
            {#each shared.scenarios as source (source.id)}
              <option value={source.scenario_id}>{source.name} ({source.scenario_id}) · {statuses[source.publication_status]}</option>
            {/each}
          </select>
          {#if selectedScenario?.description}<p class="hint">{selectedScenario.description}</p>{/if}
        </div>
      {:else}
        <p class="hint">There are no {sharedLabel.toLowerCase()} available.</p>
      {/if}
    {/if}

    <div class="field">
      <label for="explorer-question">Competency question</label>
      <select id="explorer-question" value={questionId} onchange={chooseQuestion}>
        {#each questions as option (option.id)}
          <option value={option.id}>{option.label}{option.status === 'scientific_review_pending' || pendingIds.includes(option.id) ? ' · Scientific review pending' : ''}</option>
        {/each}
      </select>
      <p>{question.question ?? originalQuestions[question.id]}</p>
      {#if question.description}<p class="hint">{question.description}</p>{/if}
      {#if scientificPending}<p role="status"><strong>Scientific review pending</strong> — {question.pending_reason ?? pendingReason}</p>{/if}
    </div>

    {#each question.parameters as parameter (parameter.id)}
      <div class="field">
        <label for="explorer-parameter-{parameter.id}">{parameter.label} (optional)</label>
        <select id="explorer-parameter-{parameter.id}" value={parameters[parameter.id] ?? ''}
          onchange={(event) => chooseParameter(parameter.id, event.currentTarget.value)}>
          <option value="">Any {parameter.label.toLowerCase()}</option>
          {#each concepts[parameter.category] as concept (concept.id)}
            <option value={concept.id}>{vocabularyLabel(parameter.category, concept.label)}</option>
          {/each}
        </select>
      </div>
    {/each}

    <button class="primary" type="submit" id="explorer-run" disabled={!canRun || pending !== null}>Run query</button>
  </form>
</section>

{#if pending || outcome}
  <section class="explorer-panel" aria-labelledby="explorer-results-heading">
    <h2 id="explorer-results-heading">Results</h2>
    {#if pending}
      <p class="status" role="status">Running query…</p>
    {:else if outcome?.kind === 'ok'}
      {@const answer = outcome.data}
      <p class="status" role="status">
        {answer.rows.length ? `${answer.rows.length} ${answer.rows.length === 1 ? 'result' : 'results'}.`
          : questionId === 'cq5' ? 'No matching execution–interaction links were found. CQ5 requires recorded links between interactions and executions of goal-required tasks. Check the selected filters and recorded relationships.'
          : 'No evidence was found for this question in the selected scenarios.'}
        {#if answer.truncated}The result limit was reached. Select a scenario or a filter to narrow the query.{/if}
      </p>
      {#each answer.notices ?? [] as notice}
        {@const source = answer.sources.find(({ id }) => id === notice.source_id)}
        <p class="hint" role="status">{#if source}<strong>{source.name}</strong> · {sourceStatus(source)} · {/if}{notice.message}</p>
      {/each}
      {#if answer.sources.length}
        <details open={answer.rows.length === 0}>
          <summary>Queried scenarios ({answer.sources.length})</summary>
          <ul class="sources">
            {#each answer.sources as source (source.id)}
              <li><strong>{source.name}</strong> · {sourceStatus(source)} <code>{source.graph_iri}</code></li>
            {/each}
          </ul>
        </details>
      {/if}
      {#if answer.rows.length}
        <!-- svelte-ignore a11y_no_noninteractive_tabindex (Keyboard users can scroll a wide result table.) -->
        <div class="results-table" role="region" aria-label="Query result rows" tabindex="0">
          <table>
            <thead>
              <tr>
                <th scope="col">Scenario</th>
                {#each answer.columns as column (column.id)}<th scope="col">{column.label}</th>{/each}
                <th scope="col">Evidence</th>
              </tr>
            </thead>
            <tbody>
              {#each answer.rows as row}
                {@const source = answer.sources.find(({ id }) => id === row.source_id)}
                <tr>
                  <td><strong>{source?.name}</strong><div class="hint">{source ? sourceStatus(source) : ''}</div></td>
                  {#each answer.columns as column (column.id)}
                    <td>
                      {#if row.values[column.id] == null}<span class="hint">Not recorded</span>
                      {:else}{row.values[column.id]}{/if}
                    </td>
                  {/each}
                  <td>
                    {#if row.evidence.length}
                      <details>
                        <summary>View evidence</summary>
                        <ul class="sources">
                          {#each row.evidence as evidence}
                            <li>{evidence.label}<code>{evidence.iri}</code></li>
                          {/each}
                        </ul>
                      </details>
                    {:else}<span class="hint">Not recorded</span>{/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    {:else if outcome}
      <p class="error" role="alert">{outcome.kind === 'rejected' ? outcome.error.message : 'The query could not be completed. Try again.'}</p>
      {#if outcome.kind === 'rejected' && outcome.status === 422 && includesDraft}
        <p class="hint">Use technical validation in the Scenario Builder to check the current draft.</p>
      {/if}
    {/if}
  </section>
{/if}
</div>

<div hidden={mode === 'questions'}>
  <CrossScenarioExplorer active={active && mode !== 'questions'} compare={mode === 'compare'} {draft}
    {uploads} {shared} loading={loadingCatalog} catalogFailed={catalog !== null && catalog.kind !== 'ok'} onretry={loadCatalog} />
</div>

<style>
  .explorer-panel {
    margin: 1rem 0;
    padding: 1rem 1.25rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: #fff;
  }

  .source-options { padding: 0; border: 0; margin: 0 0 0.4rem; }
  .source-options legend { padding: 0; }
  .field { max-width: 48rem; margin-top: 0.8rem; }
  .results-table { overflow-x: auto; margin-top: 0.8rem; }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  th, td { padding: 0.5rem; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }
  th { background: #f3f5f8; }
  td { min-width: 7rem; overflow-wrap: anywhere; }
  .sources { margin: 0.4rem 0; padding-left: 1.15rem; }
  .sources li { margin-bottom: 0.35rem; }
  .sources code { display: block; overflow-wrap: anywhere; }
</style>
