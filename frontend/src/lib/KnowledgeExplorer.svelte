<script>
  import { onDestroy } from 'svelte';
  import { fetchExplorerCatalog, requestExplorerQuery } from './api.js';
  import { concepts } from './scenario.js';
  import { vocabularyLabel } from './vocabulary-labels.js';
  import CrossScenarioExplorer from './CrossScenarioExplorer.svelte';

  /** @typedef {import('./api.js').ExplorerQuestionId} QuestionId */
  /** @typedef {import('./api.js').ExplorerScope} Scope */
  /** @typedef {import('./api.js').ExplorerRequest} Query */
  /** @typedef {ReturnType<typeof import('./scenario.js').toContract>} Draft */
  /** @typedef {Awaited<ReturnType<typeof requestExplorerQuery>>} Outcome */
  /** @type {{ active: boolean, draft: Draft | null }} */
  let { active, draft } = $props();

  // Draft queries are useful even when GraphDB cannot provide the shared catalog.
  const fallbackQuestions = /** @type {import('./api.js').ExplorerQuestion[]} */ ([
    { id: 'cq1', label: 'CQ1 · Team members and roles', description: '', parameters: [] },
    { id: 'cq2', label: 'CQ2 · Tasks supported by capabilities', description: 'Which tasks have their recorded capability requirements covered by members of the same HI team? Coverage is derived from capabilities and does not establish task execution.', parameters: [] },
    { id: 'cq5', label: 'CQ5 · Interactions during task execution', description: 'CQ5 requires recorded links between interactions and executions of goal-required tasks.', parameters: [] },
    { id: 'cq8', label: 'CQ8 · Experiments, metrics, and hypotheses', description: 'Which experiments and metrics are linked through executions that contribute to the goal or realize its required tasks?', parameters: [] },
    { id: 'cq11', label: 'CQ11 · Contextual phenomena', description: '', parameters: [] },
  ]);
  const statuses = { approved: 'Approved', reference: 'Experimental reference', provisional: 'Provisional draft' };

  let scope = $state(/** @type {Scope} */ ('draft'));
  let mode = $state(/** @type {'questions' | 'find' | 'compare'} */ ('questions'));
  let questionId = $state(/** @type {QuestionId} */ ('cq1'));
  let sharedScenarioId = $state('');
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
  let selectedScenario = $derived(shared?.scenarios.find((source) => source.scenario_id === sharedScenarioId));
  let includesDraft = $derived(scope !== 'shared');
  let includesShared = $derived(scope !== 'draft');
  let query = $derived(/** @type {Query} */ ({
    question_id: questionId, scope,
    ...(includesDraft && draft ? { scenario: draft } : {}),
    ...(includesShared && selectedScenario ? { shared_scenario_id: selectedScenario.scenario_id } : {}),
    ...(Object.keys(parameters).length ? { parameters: { ...parameters } } : {}),
  }));
  let canRun = $derived((!includesDraft || draft !== null) && (!includesShared || Boolean(shared?.scenarios.length)));
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
      <label class="inline"><input type="radio" id="explorer-source-draft" bind:group={scope} value="draft" /> My current scenario</label>
      <label class="inline"><input type="radio" id="explorer-source-approved" bind:group={scope} value="shared" /> {sharedLabel}</label>
      <label class="inline"><input type="radio" id="explorer-source-combined" bind:group={scope} value="combined" /> My current scenario and {sharedLabel.toLowerCase()}</label>
    </fieldset>

    {#if includesDraft}
      <p class="hint">{draft ? `${draft.use_case.name || 'Untitled scenario'} · Provisional draft` : 'Start or open a structured scenario in the Scenario Builder to query your draft.'}</p>
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
          <option value={option.id}>{option.label}</option>
        {/each}
      </select>
      {#if question.description}<p class="hint">{question.description}</p>{/if}
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
        <p class="hint" role="status">{#if source}<strong>{source.name}</strong> · {statuses[source.publication_status]} · {/if}{notice.message}</p>
      {/each}
      {#if answer.sources.length}
        <details open={answer.rows.length === 0}>
          <summary>Queried scenarios ({answer.sources.length})</summary>
          <ul class="sources">
            {#each answer.sources as source (source.id)}
              <li><strong>{source.name}</strong> · {statuses[source.publication_status]} <code>{source.graph_iri}</code></li>
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
                  <td><strong>{source?.name}</strong><div class="hint">{source ? statuses[source.publication_status] : ''}</div></td>
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
    {shared} loading={loadingCatalog} catalogFailed={catalog !== null && catalog.kind !== 'ok'} onretry={loadCatalog} />
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
