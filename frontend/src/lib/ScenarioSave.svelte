<script>
  import { tick } from 'svelte';
  import { fetchTeam, saveScenario } from './api.js';
  import Rejection from './Rejection.svelte';

  /**
   * @type {{
   *   json: string,
   *   issueCount: number,
   *   onIncomplete: () => void,
   *   onValidationIssues?: (issues: import('./api.js').InputIssue[], sentJson: string) => void,
   *   onNewScenarioId: (id: string) => void,
   *   fetch?: typeof globalThis.fetch,
   * }}
   */
  let { json, issueCount, onIncomplete, onValidationIssues, onNewScenarioId, fetch = undefined } = $props();

  /** @typedef {{ sentJson: string, outcome: import('./api.js').SaveResult }} SaveAttempt */
  /** @typedef {{ sentJson: string, outcome: import('./api.js').TeamResult }} TeamAttempt */
  let attempt = $state(/** @type {SaveAttempt | null} */ (null));
  let teamAttempt = $state(/** @type {TeamAttempt | null} */ (null));
  // Scenario IDs saved from this page, with the exact JSON that was saved.
  let savedInSession = $state(/** @type {Record<string, string>} */ ({}));
  let saving = $state(false);
  let loadingTeam = $state(false);
  let blocked = $state(false);

  const options = () => (fetch ? { fetch } : {});
  const RETRY_NOTE =
    'Saving again is safe: an existing scenario is never overwritten, only reported as already saved.';

  let scenarioId = $derived(/** @type {string} */ (JSON.parse(json).id));
  // Results are shown only for the exact JSON they were produced from.
  let outcome = $derived(attempt?.sentJson === json ? attempt.outcome : null);
  let saved = $derived(outcome?.kind === 'ok' ? outcome.saved : null);
  let team = $derived(saved && teamAttempt?.sentJson === json ? teamAttempt.outcome : null);
  let changedSinceSave = $derived(!saved && scenarioId in savedInSession);
  let conflict = $derived(outcome?.kind === 'rejected' && outcome.status === 409);

  async function save() {
    if (issueCount > 0) {
      blocked = true;
      onIncomplete();
      return;
    }
    blocked = false;
    saving = true;
    const sentJson = json;
    const result = await saveScenario(JSON.parse(sentJson), options());
    if (result.kind === 'ok') savedInSession[result.saved.scenario_id] = sentJson;
    attempt = { sentJson, outcome: result };
    if (result.kind === 'rejected' && result.status === 422) onValidationIssues?.(result.error.issues, sentJson);
    else if (result.kind === 'ok') onValidationIssues?.([], sentJson);
    saving = false;
  }

  async function saveAsNew() {
    // An explicit new identity: the saved scenario stays as it is.
    onNewScenarioId(crypto.randomUUID());
    await tick();
    await save();
  }

  async function showTeam() {
    if (!saved) return;
    loadingTeam = true;
    const sentJson = json;
    const requested = saved.scenario_id;
    let result = await fetchTeam(requested, options());
    if (result.kind === 'ok' && result.team.scenario_id !== requested) {
      result = { kind: 'unexpected', message: 'The backend returned a different scenario.' };
    }
    teamAttempt = { sentJson, outcome: result };
    loadingTeam = false;
  }

  /** @param {import('./api.js').TeamMember} member */
  const kind = (member) => member.types.map((t) => t.label ?? t.iri).join(', ') || '—';
</script>

<section class="save" aria-labelledby="save-heading">
  <h2 id="save-heading">2 · Save to GraphDB</h2>
  <p class="hint">
    Saving validates the scenario again on the backend and stores it as a new, read-only graph. Saved scenarios cannot
    be edited or overwritten.
  </p>

  <div aria-live="polite">
    {#if saved}
      <p class="ok">
        Saved in GraphDB · repository <code>{saved.repository_id}</code> · {saved.triple_count} triples
      </p>
      <p class="hint">Graph <code>{saved.graph_iri}</code></p>
    {:else if changedSinceSave}
      <p class="warn">
        The form has changed since scenario <code>{scenarioId}</code> was saved. The saved graph is unchanged and these
        edits are not saved.
      </p>
    {:else if !outcome}
      <p class="hint">Not saved.</p>
    {/if}

    <div class="toolbar">
      {#if changedSinceSave || conflict}
        <button type="button" class="primary" onclick={saveAsNew} disabled={saving}>
          {saving ? 'Saving…' : 'Save as new scenario'}
        </button>
      {:else if !saved}
        <button type="button" class="primary" onclick={save} disabled={saving}>
          {saving ? 'Saving…' : 'Save to GraphDB'}
        </button>
      {/if}
    </div>

    {#if blocked && issueCount > 0}
      <p class="warn">Complete the highlighted fields first ({issueCount} remaining).</p>
    {:else if outcome?.kind === 'rejected'}
      {@const { status, error } = outcome}
      {#if status === 409}
        <Rejection
          {error}
          title="Not saved: this scenario ID already exists in GraphDB."
          note="Saved scenarios are never overwritten. Save as new scenario assigns a new scenario ID and saves the form as a separate scenario."
        />
      {:else if status === 422}
        <Rejection {error} title="Not saved: the backend rejected the scenario." />
      {:else if status === 503}
        <Rejection {error} title="Not saved: GraphDB is unavailable." note={RETRY_NOTE} />
      {:else}
        <Rejection {error} title="The save did not complete; its outcome is uncertain." note={RETRY_NOTE} />
      {/if}
    {:else if outcome && outcome.kind !== 'ok'}
      <p class="error-title">The save did not complete.</p>
      <p class="error">{outcome.message}</p>
      <p class="hint">If the request reached the backend, the scenario may have been saved. {RETRY_NOTE}</p>
    {/if}
  </div>

  {#if saved}
    <h3>3 · Explore the saved scenario</h3>
    <div class="toolbar">
      <button type="button" onclick={showTeam} disabled={loadingTeam}>
        {loadingTeam ? 'Querying…' : 'Show team composition (CQ1)'}
      </button>
      <a class="button" href={saved.workbench_graph_url} target="_blank" rel="noopener noreferrer">
        Open in GraphDB Workbench ↗
      </a>
    </div>
    <p class="hint">
      Workbench opens this scenario's graph. If it asks you to choose a repository, choose
      <code>{saved.repository_id}</code>; the graph then opens.
    </p>

    <div aria-live="polite">
      {#if team?.kind === 'ok'}
        <p class="status">
          CQ1 over the saved graph: {team.team.members.length} members{team.team.use_case_name
            ? ` · ${team.team.use_case_name}`
            : ''}
        </p>
        <table class="team">
          <thead><tr><th>Member</th><th>Agent type</th><th>Roles</th></tr></thead>
          <tbody>
            {#each team.team.members as member (member.iri)}
              <tr>
                <td title={member.iri}>{member.name ?? member.iri}</td>
                <td>{kind(member)}</td>
                <td>
                  {#each member.roles as role, i (role.iri)}
                    <span title={role.definition ?? role.iri}>{role.label ?? role.iri}</span>{i < member.roles.length - 1 ? ', ' : ''}
                  {:else}—{/each}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      {:else if team?.kind === 'rejected'}
        <Rejection
          error={team.error}
          title="The team query failed. The scenario is still saved."
        />
      {:else if team}
        <p class="error-title">The team query failed. The scenario is still saved.</p>
        <p class="error">{team.message}</p>
      {/if}
    </div>
  {/if}
</section>
