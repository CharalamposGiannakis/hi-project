<script>
  import { concepts } from './scenario.js';
  import { vocabularyLabel } from './vocabulary-labels.js';

  /**
   * @type {{
   *   label: string,
   *   category: import('./scenario.js').Category,
   *   values: string[],
   *   error?: string,
   *   path?: string,
   * }}
   */
  let { label, category, values = $bindable(), error = '', path } = $props();
  const id = $props.id();

  /** @param {string} id */
  function toggle(id) {
    values = values.includes(id) ? values.filter((value) => value !== id) : [...values, id];
  }
</script>

<fieldset class="concepts" class:roles={category === 'Role'} data-field-path={path} tabindex="-1" aria-describedby={error ? `${id}-error` : undefined}>
  <legend>{label}</legend>
  {#each concepts[category] as concept (concept.id)}
    <label class="inline">
      <input type="checkbox" value={concept.id} checked={values.includes(concept.id)} onchange={() => toggle(concept.id)} aria-describedby={error ? `${id}-error` : undefined} />
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
  {#if error}<p class="error" id="{id}-error">{error}</p>{/if}
</fieldset>
