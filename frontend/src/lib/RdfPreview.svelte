<script>
  import { requestPreview } from './api.js';

  /**
   * @type {{
   *   target: { contract: object },
   *   issueCount: number,
   *   onIncomplete: () => void,
   *   onValidationIssues?: (issues: import('./api.js').InputIssue[], target: object) => void,
   *   fetch?: typeof globalThis.fetch,
   * }}
   */
  let { target, issueCount, onIncomplete, onValidationIssues, fetch = undefined } = $props();

  /** @typedef {{ target: object, outcome: import('./api.js').PreviewResult | { kind: 'incomplete' } }} Result */
  let result = $state.raw(/** @type {Result | null} */ (null));
  let loading = $state(false);
  let copied = $state('');

  let current = $derived(result?.target === target ? result.outcome : null);
  let stale = $derived(result !== null && current === null);
  let rejectedInput = $derived(current?.kind === 'rejected' && current.status === 422
    && ['invalid_request', 'invalid_vocabulary', 'shacl_failed'].includes(current.error.code));
  let needsCorrections = $derived(current?.kind === 'incomplete' || rejectedInput);
  let status = $derived(loading ? 'Validating…' : needsCorrections ? 'Needs corrections'
    : current?.kind === 'ok' ? 'Valid' : current ? 'Technical validation error' : 'Not validated');

  async function preview() {
    copied = '';
    const submitted = target;
    onValidationIssues?.([], submitted);
    if (issueCount > 0) {
      result = { target: submitted, outcome: { kind: 'incomplete' } };
      onIncomplete();
      return;
    }
    result = null;
    loading = true;
    const outcome = await requestPreview(submitted.contract, fetch ? { fetch } : {});
    result = { target: submitted, outcome };
    if (submitted === target && outcome.kind === 'rejected' && outcome.status === 422) {
      onValidationIssues?.(outcome.error.issues, submitted);
    }
    loading = false;
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
  <h2 id="preview-heading">Technical validation</h2>
  <p class="hint">
    Checks the HI model, HINT vocabulary, and SHACL shapes. Scientific approval requires a separate review.
  </p>
  <div class="toolbar">
    <button type="button" class="primary" onclick={preview} disabled={loading}>Validate Scenario</button>
  </div>

  <p data-validation-status class:ok={status === 'Valid'} class:warn={needsCorrections} class:error-title={status === 'Technical validation error'} role="status">{status}</p>
  <div aria-live="polite">
    {#if current?.kind === 'incomplete'}
      <p class="hint">Review the highlighted fields before validating again.</p>
    {:else if stale && !loading}
      <p class="hint">The scenario has changed. Validate again to see current results.</p>
    {:else if current?.kind === 'ok'}
      {@const preview = current.preview}
      <p class="hint">Conforms to the HI SHACL shapes. Generated {preview.triple_count} {preview.triple_count === 1 ? 'triple' : 'triples'}.</p>
      <details>
        <summary>RDF preview</summary>
        <div class="toolbar">
          <button type="button" onclick={() => copyRdf(preview.rdf)}>Copy RDF</button>
          <button type="button" onclick={() => downloadRdf(preview)}>Download .nt</button>
        </div>
        {#if copied}<p class="status" role="status">{copied}</p>{/if}
        <pre class="rdf" aria-label="Generated RDF (N-Triples)">{preview.rdf}</pre>
      </details>
      <details>
        <summary>SHACL report</summary>
        <pre class="report">{preview.validation.report}</pre>
      </details>
    {:else if current?.kind === 'rejected'}
      <p class="error">{current.error.message}</p>
      {#if current.error.shacl_report}
        <details open>
          <summary>SHACL report</summary>
          <pre class="report">{current.error.shacl_report}</pre>
        </details>
      {/if}
    {:else if current}
      <p class="error">{current.message}</p>
    {/if}
  </div>
</section>
