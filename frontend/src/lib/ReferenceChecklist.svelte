<script>
  /**
   * @type {{
   *   label: string,
   *   options: { id: string, name: string }[],
   *   values: string[],
   *   error?: string,
   * }}
   */
  let { label, options, values = $bindable(), error = '' } = $props();

  /** @param {string} id */
  function toggle(id) {
    values = values.includes(id) ? values.filter((value) => value !== id) : [...values, id];
  }
</script>

<fieldset class="concepts">
  <legend>{label}</legend>
  {#each options as option (option.id)}
    <label class="inline">
      <input type="checkbox" value={option.id} checked={values.includes(option.id)} onchange={() => toggle(option.id)} />
      {option.name.trim() || 'Unnamed'} <code>({option.id})</code>
    </label>
  {/each}
  {#if error}<p class="error">{error}</p>{/if}
</fieldset>
