<script>
  import { concepts, findConcept } from './scenario.js';

  /**
   * @type {{
   *   label: string,
   *   category: import('./scenario.js').Category,
   *   value: string,
   *   optional?: boolean,
   *   error?: string,
   * }}
   */
  let { label, category, value = $bindable(), optional = false, error = '' } = $props();

  const id = `concept-${Math.random().toString(36).slice(2)}`;
  let selected = $derived(findConcept(category, value));
</script>

<div class="field">
  <label for={id}>{label}{optional ? ' (optional)' : ''}</label>
  <select {id} bind:value aria-invalid={error ? 'true' : undefined}>
    <option value="">{optional ? '— none —' : '— choose a HINT concept —'}</option>
    {#each concepts[category] as concept (concept.id)}
      <option value={concept.id}>{concept.label}</option>
    {/each}
  </select>
  {#if selected}
    <p class="hint"><code>hint:{selected.id}</code> — {selected.definition}</p>
  {/if}
  {#if error}<p class="error">{error}</p>{/if}
</div>
