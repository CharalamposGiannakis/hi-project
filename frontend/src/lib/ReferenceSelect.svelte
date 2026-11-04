<script>
  /**
   * @type {{
   *   label: string,
   *   options: { id: string, name: string }[],
   *   value: string,
   *   error?: string,
   *   path?: string,
   * }}
   */
  let { label, options, value = $bindable(), error = '', path } = $props();
  const id = $props.id();
  let missing = $derived(value !== '' && !options.some((option) => option.id === value));
</script>

<div class="field" data-field-path={path}>
  <label for={id}>{label}</label>
  <select {id} bind:value aria-invalid={missing || error ? 'true' : undefined} aria-describedby={missing || error ? `${id}-error` : undefined}>
    <option value="">— choose an existing {label.toLowerCase()} —</option>
    {#if missing}<option value={value}>Missing {label.toLowerCase()} ({value})</option>{/if}
    {#each options as option (option.id)}
      <option value={option.id}>{option.name.trim() || 'Unnamed'} ({option.id})</option>
    {/each}
  </select>
  {#if missing}
    <p class="error" id="{id}-error">{label} "{value}" no longer exists. Choose a replacement or remove this record.</p>
  {:else if error}
    <p class="error" id="{id}-error">{error}</p>
  {/if}
</div>
