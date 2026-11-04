<script>
  import { onMount } from 'svelte';
  import { requestScenarioJson } from './lib/json-viewer-channel.js';

  const sourceId = window.location.hash.slice(1);
  let snapshot = $state('');
  let phase = $state('loading');
  let retrievedAt = $state('');
  let error = $state('');
  /** @type {AbortController | undefined} */
  let pending;

  async function refresh() {
    pending?.abort();
    const request = new AbortController();
    pending = request;
    phase = 'loading';
    error = '';
    try {
      const json = await requestScenarioJson(sourceId, { signal: request.signal });
      if (request.signal.aborted) return;
      snapshot = json;
      retrievedAt = new Date().toLocaleString();
      phase = 'ready';
    } catch {
      if (request.signal.aborted) return;
      phase = 'error';
      error = sourceId
        ? 'Could not retrieve JSON. The original Scenario Builder tab may be closed or unavailable. Keep it open and try Refresh JSON again.'
        : 'Open this viewer using “Open JSON in new tab” in the Scenario Builder.';
    }
  }

  onMount(() => {
    refresh();
    return () => pending?.abort();
  });
</script>

<main class="json-viewer">
  <h1>Scenario JSON</h1>
  <p>Refresh JSON retrieves the latest scenario state, including unsaved edits. Changes in the Builder do not update this snapshot automatically.</p>
  <p>Keep the original Scenario Builder tab open. If you reload that tab, open a new viewer from it.</p>
  <button type="button" onclick={refresh} disabled={phase === 'loading'}>Refresh JSON</button>
  <div aria-live="polite" aria-busy={phase === 'loading'}>
    {#if phase === 'loading'}
      <p class="status" role="status">Retrieving the latest JSON…</p>
    {:else if phase === 'ready'}
      <p class="ok" role="status">Snapshot retrieved {retrievedAt}. Refresh again to retrieve later edits.</p>
    {:else}
      <p class="error" role="alert">{error}</p>
    {/if}
  </div>
  {#if snapshot}
    <h2 id="snapshot-heading">{phase === 'ready' ? 'Scenario snapshot (read-only)' : 'Previous snapshot — latest state not confirmed'}</h2>
    {#if phase !== 'ready'}<p class="warn">This snapshot was retrieved {retrievedAt}; it may be out of date.</p>{/if}
    <!-- svelte-ignore a11y_no_noninteractive_tabindex (Keyboard access to scrollable JSON text.) -->
    <pre class="viewer-json" role="region" tabindex="0" aria-labelledby="snapshot-heading">{snapshot}</pre>
  {/if}
</main>

<style>
  .json-viewer { display: block; max-width: none; box-sizing: border-box; padding: 1.5rem; }
  h2 { margin-top: 1.25rem; }
  p { max-width: 90ch; }
  .viewer-json { max-height: 75dvh; overflow: auto; white-space: pre; padding: 1rem; border: 1px solid var(--border); border-radius: 6px; background: #fff; font-size: 0.85rem; }
</style>
