<script>
  import { issuePath } from './api.js';
  /** @type {{ title: string, error: import('./api.js').SubmissionError, note?: string }} */
  let { title, error, note = '' } = $props();

</script>

<p class="error-title">{title}</p>
<p class="error">{error.message}</p>
{#if error.issues.length}
  <ul class="issues">
    {#each error.issues as issue, i (i)}<li><code>{issuePath(issue.location)}</code> {issue.message}</li>{/each}
  </ul>
{/if}
{#if error.shacl_report}
  <details open>
    <summary>SHACL report</summary>
    <pre class="report">{error.shacl_report}</pre>
  </details>
{/if}
{#if note}<p class="hint">{note}</p>{/if}
