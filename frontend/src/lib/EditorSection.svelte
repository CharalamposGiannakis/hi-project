<script>
  /** @type {{
   * id: string, title: string, count?: number, optional?: boolean,
   * open?: boolean, errorCount?: number, revealRequest?: number,
   * children: import('svelte').Snippet,
   * }} */
  let { id, title, count, optional = false, open = $bindable(false), errorCount = 0, revealRequest = 0, children } = $props();

  // A new error count or an explicit validation request discloses this section.
  // Researchers can still collapse it until the next check or validation change.
  $effect(() => {
    revealRequest;
    if (errorCount > 0) open = true;
  });
</script>

<details class="editor-section" id="section-{id}" bind:open>
  <summary aria-expanded={open} aria-controls="section-body-{id}">
    <h2>{title}</h2>
    {#if count !== undefined}<span class="count" aria-label="{count} items">{count}</span>{/if}
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
