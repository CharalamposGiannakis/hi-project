<script>
  import { concepts, findConcept } from './scenario.js';

  /**
   * @type {{
   *   label: string,
   *   category: import('./scenario.js').Category,
   *   values: string[],
   *   error?: string,
   * }}
   */
  let { label, category, values = $bindable(), error = '' } = $props();

  /** @param {string} id */
  function toggle(id) {
    values = values.includes(id) ? values.filter((value) => value !== id) : [...values, id];
  }
</script>

<fieldset class="concepts">
  <legend>{label}</legend>
  {#each concepts[category] as concept (concept.id)}
    <label class="inline" title={concept.definition}>
      <input type="checkbox" checked={values.includes(concept.id)} onchange={() => toggle(concept.id)} />
      {concept.label}
    </label>
  {/each}
  {#each values as id, i (i)}
    {@const concept = findConcept(category, id)}
    <p class="hint"><code>hint:{id}</code> — {concept?.definition ?? 'not a HINT concept'}</p>
  {/each}
  {#if error}<p class="error">{error}</p>{/if}
</fieldset>
