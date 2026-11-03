<script>
  import { concepts } from './scenario.js';
  import { vocabularyLabel } from './vocabulary-labels.js';

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

<fieldset class="concepts" class:roles={category === 'Role'}>
  <legend>{label}</legend>
  {#each concepts[category] as concept (concept.id)}
    <label class="inline">
      <input type="checkbox" value={concept.id} checked={values.includes(concept.id)} onchange={() => toggle(concept.id)} />
      {vocabularyLabel(category, concept.label)}
    </label>
  {/each}
  <details class="concept-help">
    <summary>HINT definitions for {label.toLowerCase()}</summary>
    <dl class="hint">
      {#each concepts[category] as concept (concept.id)}
        <dt><strong>{concept.label}</strong> · <code>hint:{concept.id}</code></dt>
        <dd>{concept.definition}</dd>
      {/each}
    </dl>
  </details>
  {#if error}<p class="error">{error}</p>{/if}
</fieldset>
