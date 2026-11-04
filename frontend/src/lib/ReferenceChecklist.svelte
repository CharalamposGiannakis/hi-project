<script>
  /**
   * @type {{
   *   label: string,
   *   options: { id: string, name: string }[],
   *   values: string[],
   *   error?: string,
   *   path?: string,
   * }}
   */
  let { label, options, values = $bindable(), error = '', path } = $props();
  const id = $props.id();
  let missing = $derived([...new Set(values.filter((id) => !options.some((option) => option.id === id)))]);

  /** @param {string} id */
  function toggle(id) {
    values = values.includes(id) ? values.filter((value) => value !== id) : [...values, id];
  }
</script>

<fieldset class="concepts" data-field-path={path} tabindex="-1" aria-describedby={missing.length || error ? `${id}-error` : undefined}>
  <legend>{label}</legend>
  {#each options as option (option.id)}
    <label class="inline">
      <input type="checkbox" value={option.id} checked={values.includes(option.id)} onchange={() => toggle(option.id)} aria-describedby={missing.length || error ? `${id}-error` : undefined} />
      {option.name.trim() || 'Unnamed'} <code>({option.id})</code>
    </label>
  {/each}
  {#each missing as missingId (missingId)}
    <label class="inline">
      <input type="checkbox" value={missingId} checked onchange={() => toggle(missingId)} aria-describedby="{id}-error" />
      Missing reference ({missingId})
    </label>
  {/each}
  {#if missing.length}
    <p class="error" id="{id}-error">Referenced records no longer exist: {missing.join(', ')}. Select replacements and uncheck missing references, or remove this record.</p>
  {/if}
  {#if error}<p class="error" id={missing.length ? undefined : `${id}-error`}>{error}</p>{/if}
</fieldset>
