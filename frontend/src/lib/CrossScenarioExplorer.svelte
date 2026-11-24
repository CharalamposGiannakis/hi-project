<script>
  import { onDestroy } from 'svelte';
  import { requestConceptExploration } from './api.js';
  import { concepts } from './scenario.js';
  import { vocabularyLabel } from './vocabulary-labels.js';

  /** @typedef {import('./api.js').ConceptExplorationRequest} Query */
  /** @typedef {import('./api.js').ExplorationCategory} Category */
  /** @typedef {ReturnType<typeof import('./scenario.js').toContract>} Draft */
  /** @typedef {Awaited<ReturnType<typeof requestConceptExploration>>} Outcome */
  /** @type {{ active: boolean, compare: boolean, draft: Draft | null,
   * uploads?: import('./api.js').SessionUpload[],
   * shared: import('./api.js').ExplorerCatalog | null, loading: boolean, catalogFailed: boolean,
   * onretry: () => Promise<void> }} */
  let { active, compare, draft, uploads = [], shared, loading, catalogFailed, onretry } = $props();

  const categories = /** @type {{ id: Category, label: string }[]} */ ([
    { id: 'Capability', label: 'Capabilities' }, { id: 'Constraint', label: 'Constraints' },
    { id: 'Method', label: 'Methods' }, { id: 'Metric', label: 'Evaluation metrics' },
  ]);
  const statuses = { approved: 'Approved', reference: 'Experimental reference', provisional: 'Provisional draft' };
  /** @param {import('./api.js').ExplorerSource} source */
  const sourceStatus = (source) => source.publication_status === 'provisional' && source.file_name
    ? 'Provisional upload' : statuses[source.publication_status];
  let scope = $state(/** @type {import('./api.js').ExplorerScope} */ ('shared'));
  let searchCategory = $state(/** @type {Category} */ ('Capability'));
  let comparisonCategory = $state(/** @type {Category | ''} */ (''));
  let concept = $state('');
  let sharedScenarioId = $state('');
  let includeCurrent = $state(true);
  let firstSourceId = $state('');
  let selected = $derived(shared?.scenarios.find((source) => source.scenario_id === sharedScenarioId));
  let selectedUploads = $derived(uploads.filter((upload) => upload.selected).map(({ selected: _selected, ...upload }) => upload));
  let localSources = $derived([
    ...(draft ? [{ id: `provisional:${draft.id}`, name: `${draft.use_case.name || 'Current Builder scenario'} · Provisional draft` }] : []),
    ...selectedUploads.map((upload) => ({ id: `upload:${upload.id}`, name: `${upload.file_name} · Provisional upload` })),
  ]);
  let firstSource = $derived(localSources.find((source) => source.id === (firstSourceId || localSources[0]?.id)));
  let secondLocal = $derived(localSources.find((source) => source.id === sharedScenarioId));
  let comparisonIds = $derived([firstSource?.id, secondLocal?.id ?? selected?.id]);
  let comparisonUploads = $derived(selectedUploads.filter((upload) => comparisonIds.includes(`upload:${upload.id}`)));
  let comparisonDraft = $derived(Boolean(draft && comparisonIds.includes(`provisional:${draft.id}`)));
  let queryUploads = $derived(compare ? comparisonUploads : scope !== 'shared' ? selectedUploads : []);
  let pending = $state.raw(/** @type {{ query: Query, controller: AbortController } | null} */ (null));
  let result = $state.raw(/** @type {{ query: Query, outcome: Outcome } | null} */ (null));

  let sharedLabel = $derived(shared?.shared_source === 'approved' ? 'Approved scenarios'
    : shared?.shared_source === 'reference' ? 'Experimental reference scenarios' : 'Shared scenarios');
  let includesDraft = $derived(compare ? comparisonDraft : scope !== 'shared');
  let includesShared = $derived(compare ? Boolean(selected) : scope !== 'draft');
  let category = $derived(compare ? comparisonCategory : searchCategory);
  let query = $derived(/** @type {Query} */ ({
    scope: compare ? (selected ? 'combined' : 'draft') : scope,
    compare,
    category: category || null,
    ...(includesDraft && draft && (compare || includeCurrent) ? { scenario: draft } : {}),
    ...(queryUploads.length ? { uploads: queryUploads } : {}),
    ...(includesShared && selected ? { shared_scenario_id: selected.scenario_id } : {}),
    ...(!compare && concept ? { concept } : {}),
    ...(compare && comparisonUploads.length && firstSource && (secondLocal || selected)
      ? { comparison_source_ids: /** @type {[string, string]} */ ([firstSource.id, secondLocal?.id ?? selected?.id]) } : {}),
  }));
  let canRun = $derived(compare
    ? Boolean(firstSource && (secondLocal || selected) && firstSource.id !== (secondLocal?.id ?? selected?.id))
    : (scope === 'shared' || (includeCurrent && draft !== null) || selectedUploads.length > 0)
      && (!includesShared || Boolean(shared?.scenarios.length)));
  let outcome = $derived(result?.query === query ? result.outcome : null);

  $effect(() => {
    if (pending && (pending.query !== query || !active)) {
      pending.controller.abort();
      pending = null;
    }
  });
  onDestroy(() => pending?.controller.abort());

  /** @param {Event} event */
  function chooseCategory(event) {
    if (!(event.currentTarget instanceof HTMLSelectElement)) return;
    const value = event.currentTarget.value;
    if (compare) comparisonCategory = /** @type {Category | ''} */ (value);
    else {
      searchCategory = /** @type {Category} */ (value);
      concept = '';
    }
  }

  async function run() {
    if (!canRun || pending) return;
    const submitted = query;
    const controller = new AbortController();
    pending = { query: submitted, controller };
    result = null;
    const response = await requestConceptExploration(submitted, { signal: controller.signal });
    if (pending?.controller !== controller) return;
    pending = null;
    if (submitted === query) result = { query: submitted, outcome: response };
  }
</script>

<section class="explorer-panel" aria-labelledby="cross-scenario-heading">
  <h2 id="cross-scenario-heading">{compare ? 'Compare scenarios' : 'Find concepts across scenarios'}</h2>
  <p class="hint">Matching HINT concepts indicate recorded vocabulary overlap. Scientific equivalence, knowledge transfer, and effectiveness require separate evidence.</p>
  <form onsubmit={(event) => { event.preventDefault(); void run(); }}>
    {#if !compare}
      <div class="field">
        <label for="concept-scope">Query source</label>
        <select id="concept-scope" bind:value={scope}>
          <option value="shared">{sharedLabel}</option>
          <option value="draft">My current scenario and selected uploads</option>
          <option value="combined">My current scenario, selected uploads, and {sharedLabel.toLowerCase()}</option>
        </select>
      </div>
    {/if}
    {#if compare}
      <div class="field">
        <label for="comparison-first">First scenario</label>
        <select id="comparison-first" value={firstSource?.id ?? ''} onchange={(event) => { firstSourceId = event.currentTarget.value; }}>
          <option value="">Choose a provisional scenario</option>
          {#each localSources as source (source.id)}<option value={source.id}>{source.name}</option>{/each}
        </select>
      </div>
      {#if !localSources.length}<p class="hint">Start or open a structured scenario in the Scenario Builder, or upload a valid scenario.</p>{/if}
    {/if}
    {#if includesDraft}
      {#if !compare}<label class="inline"><input id="concept-include-current" type="checkbox" bind:checked={includeCurrent} /> Include current Builder scenario</label>{/if}
      <p class="hint">{draft ? `${draft.use_case.name || 'Untitled scenario'} · Provisional draft`
        : 'Start or open a structured scenario in the Scenario Builder to include your draft.'}</p>
    {/if}
    {#if !compare && scope !== 'shared' && selectedUploads.length}<p class="hint">{selectedUploads.length} selected provisional uploads will participate.</p>{/if}
    {#each shared?.warnings ?? [] as warning}
      <p class="hint" role="status">{warning}</p>
    {/each}
    {#if includesShared || compare}
      {#if loading}<p class="status" role="status">Loading shared scenarios…</p>
      {:else if catalogFailed}
        <p class="error" role="alert">Shared scenarios could not be loaded.</p>
        <button class="link" type="button" onclick={onretry}>Retry loading shared scenarios</button>
      {/if}
      {#if shared?.scenarios.length || (compare && localSources.length > 1)}
        <div class="field">
          <label for="concept-scenario">{compare ? 'Second scenario' : 'Scenario'}</label>
          <select id="concept-scenario" bind:value={sharedScenarioId}>
            <option value="">{compare ? 'Choose a scenario to compare' : `All ${sharedLabel.toLowerCase()}`}</option>
            {#if compare}
              {#each localSources.filter((source) => source.id !== firstSource?.id) as source (source.id)}
                <option value={source.id}>{source.name}</option>
              {/each}
            {/if}
            {#each shared?.scenarios ?? [] as source (source.id)}
              <option value={source.scenario_id}>{source.name} ({source.scenario_id}) · {statuses[source.publication_status]}</option>
            {/each}
          </select>
          {#if selected?.description}<p class="hint">{selected.description}</p>{/if}
        </div>
      {:else if !loading && !catalogFailed}<p class="hint">There are no shared scenarios available.</p>{/if}
    {/if}
    <div class="field">
      <label for="concept-category">Concept type</label>
      <select id="concept-category" value={category} onchange={chooseCategory}>
        {#if compare}<option value="">All four concept types</option>{/if}
        {#each categories as item (item.id)}<option value={item.id}>{item.label}</option>{/each}
      </select>
    </div>
    {#if !compare}
      <div class="field">
        <label for="concept-value">HINT concept</label>
        <select id="concept-value" bind:value={concept}>
          <option value="">All recorded concepts of this type</option>
          {#each concepts[searchCategory] as item (item.id)}
            <option value={item.id}>{vocabularyLabel(searchCategory, item.label)}</option>
          {/each}
        </select>
      </div>
    {/if}
    <button class="primary" type="submit" id="concept-run" disabled={!canRun || pending !== null}>
      {compare ? 'Compare scenarios' : 'Find concepts'}
    </button>
  </form>
</section>

{#if pending || outcome}
  <section class="explorer-panel" aria-labelledby="concept-results-heading">
    <h2 id="concept-results-heading">Results</h2>
    {#if pending}
      <p class="status" role="status">{compare ? 'Comparing scenarios…' : 'Finding concepts…'}</p>
    {:else if outcome?.kind === 'ok'}
      {@const answer = outcome.data}
      {@const columns = answer.columns.filter((column) => compare || column.id !== 'overlap')}
      <p class="status" role="status">
        {answer.rows.length ? `${answer.rows.length} recorded concept relationships.` : 'No matching concepts were recorded in the selected scenarios.'}
        {#if answer.truncated}The result limit was reached. Only the first 200 rows are shown, so some selected scenarios may not appear. Select a scenario, concept, or concept type to narrow the results.{/if}
      </p>
      {#if compare}<p class="hint">“Only” means the concept is recorded in one selected scenario. Missing records leave the other scenario’s knowledge unresolved.</p>{/if}
      {#each answer.notices ?? [] as notice}
        {@const source = answer.sources.find(({ id }) => id === notice.source_id)}
        <p class="hint" role="status">{#if source}<strong>{source.name}</strong> · {sourceStatus(source)} · {/if}{notice.message}</p>
      {/each}
      <details open={answer.rows.length === 0}>
        <summary>Queried scenarios ({answer.sources.length})</summary>
        <ul class="sources">
          {#each answer.sources as source (source.id)}
            <li><strong>{source.name}</strong> · {sourceStatus(source)}<code>{source.graph_iri}</code></li>
          {/each}
        </ul>
      </details>
      {#if answer.rows.length}
        <!-- svelte-ignore a11y_no_noninteractive_tabindex (Keyboard users can scroll a wide result table.) -->
        <div class="results-table" role="region" aria-label="Concept relationships" tabindex="0">
          <table>
            <thead><tr><th scope="col">Scenario</th>
              {#each columns as column (column.id)}<th scope="col">{column.label}</th>{/each}
              <th scope="col">Evidence</th>
            </tr></thead>
            <tbody>
              {#each answer.rows as row}
                {@const source = answer.sources.find(({ id }) => id === row.source_id)}
                <tr>
                  <td><strong>{source?.name}</strong><div class="hint">{source ? sourceStatus(source) : ''}</div></td>
                  {#each columns as column (column.id)}
                    <td>{#if row.values[column.id] == null}<span class="hint">Not recorded</span>{:else}{row.values[column.id]}{/if}</td>
                  {/each}
                  <td><details><summary>View evidence</summary><ul class="sources">
                    {#each row.evidence as item}<li>{item.label}<code>{item.iri}</code></li>{/each}
                  </ul></details></td>
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

<style>
  .explorer-panel { margin: 1rem 0; padding: 1rem 1.25rem; border: 1px solid var(--border); border-radius: 6px; background: #fff; }
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
