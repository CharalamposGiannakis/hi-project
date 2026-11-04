<script>
  import { untrack } from 'svelte';

  /** @type {{
   * id: string, title: string, count?: number, optional?: boolean,
   * open?: boolean, issues?: import('./scenario.js').Issue[], revealRequest?: number,
   * children: import('svelte').Snippet,
   * }} */
  let { id, title, count, optional = false, open = $bindable(false), issues = [], revealRequest = 0, children } = $props();
  let errorCount = $derived(issues.length);
  let previousRequest = -1;
  let previousIssues = new Set();

  // A newly appearing issue or an explicit check discloses the section. Recomputing
  // the same issues (or resolving some) must respect the researcher's collapse.
  $effect(() => {
    const keys = issues.map((issue) => JSON.stringify([issue.path, issue.message]));
    const reveal = keys.length > 0 && (revealRequest !== previousRequest || keys.some((key) => !previousIssues.has(key)));
    previousRequest = revealRequest;
    previousIssues = new Set(keys);
    // Updating a bound prop can read parent state; don't add that to this effect.
    if (reveal) untrack(() => { open = true; });
  });
</script>

<details class="editor-section" id="section-{id}" bind:open>
  <summary aria-expanded={open} aria-controls="section-body-{id}">
    <h2>{title}</h2>
    {#if count !== undefined}<span class="count" aria-label="{count} {count === 1 ? 'item' : 'items'}">{count}</span>{/if}
    {#if optional}<span class="section-optional">optional</span>{/if}
    {#if errorCount > 0}<span class="error-count">{errorCount} {errorCount === 1 ? 'issue' : 'issues'}</span>{/if}
  </summary>
  <div class="section-body" id="section-body-{id}">
    <fieldset>
      <legend class="sr-only">{title}</legend>
      {@render children()}
    </fieldset>
  </div>
</details>
