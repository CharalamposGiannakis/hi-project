<script>
  import { workspacePages } from './workspace-pages.js';

  /** @type {{ onNavigate: (view: import('./workspace-pages.js').ViewId) => void }} */
  let { onNavigate } = $props();

  const pillars = workspacePages.filter((page) => page.id !== 'home');
</script>

<p class="home-introduction">{workspacePages[0].description}</p>

<div class="pillar-guidance">
  {#each pillars as pillar (pillar.id)}
    <section aria-labelledby="home-{pillar.id}-heading">
      <h2 id="home-{pillar.id}-heading">{pillar.label}</h2>
      {#if pillar.status}<p class="planned">{pillar.status}</p>{/if}
      <p>{pillar.description}</p>
      <button type="button" onclick={() => onNavigate(pillar.id)}>{pillar.action}</button>
    </section>
  {/each}
</div>

<p class="workspace-note">Technical validation checks the scenario representation. Scientific approval requires separate review.</p>
<p class="hint">Your draft and experimental session scenarios stay available as you navigate. Download your draft JSON before closing or reloading the app.</p>

<style>
  .home-introduction { max-width: 65ch; margin: 0 0 1.25rem; font-size: 1.05rem; }
  .pillar-guidance { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 16rem), 1fr)); gap: 1rem; }
  section { display: flex; flex-direction: column; align-items: start; padding: 1.25rem; border: 1px solid var(--border); border-radius: 6px; background: #fff; }
  h2 { margin: 0; }
  section p { margin: 0.75rem 0 1rem; }
  section .planned { margin: 0.5rem 0 0; color: var(--muted); font-size: 0.85rem; }
  button { margin-top: auto; }
  .workspace-note { margin: 1.25rem 0 0.4rem; }
</style>
