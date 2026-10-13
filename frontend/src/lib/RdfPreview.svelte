<script>
  import { requestPreview } from './api.js';

  /**
   * @type {{
   *   json: string,
   *   issueCount: number,
   *   onIncomplete: () => void,
   *   fetch?: typeof globalThis.fetch,
   * }}
   */
  let { json, issueCount, onIncomplete, fetch = undefined } = $props();

  /** @typedef {{ sentJson: string, outcome: import('./api.js').PreviewResult }} Result */
  let result = $state(/** @type {Result | null} */ (null));
  let loading = $state(false);
  let blocked = $state(false);
  let copied = $state('');

  // A result belongs to the exact JSON that was sent; any later edit makes it stale.
  let current = $derived(result && result.sentJson === json ? result.outcome : null);
  let stale = $derived(result !== null && current === null);

  async function preview() {
    copied = '';
    if (issueCount > 0) {
      blocked = true;
      onIncomplete();
      return;
    }
    blocked = false;
    loading = true;
    const sentJson = json;
    const outcome = await requestPreview(JSON.parse(sentJson), fetch ? { fetch } : {});
    result = { sentJson, outcome };
    loading = false;
  }

  /** @param {(string | number)[]} location */
  function field(location) {
    return location.filter((part) => part !== 'body').join('.') || 'scenario';
  }

  /** @param {string} rdf */
  async function copyRdf(rdf) {
    try {
      await navigator.clipboard.writeText(rdf);
      copied = 'RDF copied to the clipboard.';
    } catch {
      copied = 'Copy failed; select the RDF text manually.';
    }
  }

  /** @param {import('./api.js').ScenarioPreview} preview */
  function downloadRdf(preview) {
    const url = URL.createObjectURL(new Blob([preview.rdf], { type: 'application/n-triples' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `scenario-${preview.scenario_id}.nt`;
    link.click();
    URL.revokeObjectURL(url);
  }
</script>

<section class="preview" aria-labelledby="preview-heading">
  <h2 id="preview-heading">RDF preview</h2>
  <p class="hint">
    Sends the scenario to the local Python backend, which generates RDF and validates it against the HI SHACL shapes.
    <strong>Previewing does not save the scenario.</strong>
  </p>
  <div class="toolbar">
    <button type="button" class="primary" onclick={preview} disabled={loading}>
      {loading ? 'Validating…' : 'Validate & preview RDF'}
    </button>
  </div>

  <div aria-live="polite">
    {#if blocked && issueCount > 0}
      <p class="warn">Complete the highlighted fields first ({issueCount} remaining); the backend checks complete scenarios only.</p>
    {:else if stale && !loading}
      <p class="warn">The scenario has changed since the last preview. Validate again to see current results.</p>
    {:else if current?.kind === 'ok'}
      <p class="ok">
        Valid: conforms to the HI SHACL shapes · {current.preview.triple_count} triples · not saved
      </p>
      <div class="toolbar">
        <button type="button" onclick={() => current?.kind === 'ok' && copyRdf(current.preview.rdf)}>Copy RDF</button>
        <button type="button" onclick={() => current?.kind === 'ok' && downloadRdf(current.preview)}>Download .nt</button>
      </div>
      {#if copied}<p class="status" role="status">{copied}</p>{/if}
      <pre class="rdf" aria-label="Generated RDF (N-Triples)">{current.preview.rdf}</pre>
      <details>
        <summary>SHACL report</summary>
        <pre class="report">{current.preview.validation.report}</pre>
      </details>
    {:else if current?.kind === 'rejected'}
      {@const error = current.error}
      <p class="error-title">
        {error.code === 'internal_error' ? 'The backend failed while processing the scenario.' : 'Not valid: the backend rejected the scenario.'}
      </p>
      <p class="error">{error.message}</p>
      {#if error.issues.length}
        <ul class="issues">
          {#each error.issues as issue, i (i)}<li><code>{field(issue.location)}</code> {issue.message}</li>{/each}
        </ul>
      {/if}
      {#if error.shacl_report}
        <details open>
          <summary>SHACL report</summary>
          <pre class="report">{error.shacl_report}</pre>
        </details>
      {/if}
    {:else if current}
      <p class="error-title">Preview unavailable.</p>
      <p class="error">{current.message}</p>
    {/if}
  </div>
</section>
