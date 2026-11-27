<script>
  import { workspacePages } from './workspace-pages.js';

  let { onfeedback } = $props();
  const pillars = workspacePages.filter((page) => ['builder', 'management', 'explorer'].includes(page.id));
</script>

<p class="home-introduction">{workspacePages[0].description}</p>

<div class="pillar-guidance">
  {#each pillars as pillar (pillar.id)}
    <section aria-labelledby="home-{pillar.id}-heading">
      <h2 id="home-{pillar.id}-heading">{pillar.label}</h2>
      {#if pillar.status}<p class="planned">{pillar.status}</p>{/if}
      <p>{pillar.description}</p>
    </section>
  {/each}
</div>

<p class="workspace-note">Technical validation checks the scenario representation. Scientific approval requires separate review.</p>
<p class="hint">Your draft and experimental session scenarios stay available as you navigate. Download your draft JSON before closing or reloading the app.</p>
<p>Have a problem, suggestion, or scientific observation? <button type="button" class="link" onclick={onfeedback}>Share feedback</button> with the project operator.</p>

<style>
  .home-introduction { max-width: 65ch; margin: 0 0 1.25rem; font-size: 1.05rem; }
  .pillar-guidance { display: grid; gap: 1.5rem; }
  h2 { margin: 0; }
  section p { margin: 0.4rem 0 0; }
  section .planned { margin: 0.5rem 0 0; color: var(--muted); font-size: 0.85rem; }
  .workspace-note { margin: 1.25rem 0 0.4rem; }
</style>
