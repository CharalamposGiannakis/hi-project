<script>
  /**
   * @type {{
   *   label: string,
   *   options: { id: string, name: string }[],
   *   value: string,
   *   error?: string,
   * }}
   */
  let { label, options, value = $bindable(), error = '' } = $props();
  const id = `reference-${Math.random().toString(36).slice(2)}`;
  let missing = $derived(value !== '' && !options.some((option) => option.id === value));
</script>

<div class="field">
  <label for={id}>{label}</label>
  <select {id} bind:value aria-invalid={missing || error ? 'true' : undefined}>
    <option value="">— choose an existing {label.toLowerCase()} —</option>
    {#if missing}<option value={value}>Missing {label.toLowerCase()} ({value})</option>{/if}
    {#each options as option (option.id)}
      <option value={option.id}>{option.name.trim() || 'Unnamed'} ({option.id})</option>
    {/each}
  </select>
  {#if missing}
    <p class="error">{label} "{value}" no longer exists. Choose a replacement or remove this record.</p>
  {:else if error}
    <p class="error">{error}</p>
  {/if}
</div>
