<script>
  import { concepts, findConcept } from './scenario.js';
  import { vocabularyLabel } from './vocabulary-labels.js';

  /**
   * @type {{
   *   label: string,
   *   category: import('./scenario.js').Category,
   *   value: string,
   *   optional?: boolean,
   *   error?: string,
   *   path?: string,
   * }}
   */
  let { label, category, value = $bindable(), optional = false, error = '', path } = $props();

  const id = $props.id();
  let selected = $derived(findConcept(category, value));
</script>

<div class="field" data-field-path={path}>
  <label for={id}>{label}{optional ? ' (optional)' : ''}</label>
  <select {id} bind:value aria-invalid={error ? 'true' : undefined} aria-describedby={error ? `${id}-error` : undefined}>
    <option value="">{optional ? '— none —' : '— choose a HINT concept —'}</option>
    {#each concepts[category] as concept (concept.id)}
      <option value={concept.id}>{vocabularyLabel(category, concept.label)}</option>
    {/each}
  </select>
  {#if selected}
    <details class="concept-help">
      <summary>HINT details for {label.toLowerCase()}</summary>
      <p class="hint"><strong>{selected.label}</strong> · <code>hint:{selected.id}</code></p>
      {#if selected.definition}<p class="hint">{selected.definition}</p>{/if}
    </details>
  {/if}
  {#if error}<p class="error" id="{id}-error">{error}</p>{/if}
</div>
