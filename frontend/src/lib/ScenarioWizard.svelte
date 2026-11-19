<script>
  import { tick } from 'svelte';
  import { questions } from './interpretation.js';

  /** @typedef {import('./interpretation.js').Answers} Answers */
  /** @type {{
   *   answers: Answers,
   *   onAnswer: (id: typeof questions[number]['id'], value: string) => void,
   *   onInterpret: () => void,
   *   onLoadExample: (kind: 'complete' | 'incomplete') => void,
   *   interpreting?: boolean,
   * }} */
  let { answers, onAnswer, onInterpret, onLoadExample, interpreting = false } = $props();

  let step = $state(0);
  let heading = $state(/** @type {HTMLHeadingElement | undefined} */ (undefined));
  let question = $derived(questions[step]);
  let answeredQuestions = $derived(questions.filter(({ id }) => answers[id]?.trim()));

  /** @param {number} offset */
  async function move(offset) {
    step += offset;
    await tick();
    heading?.focus();
  }
</script>

<section class="wizard" aria-labelledby="description-heading">
  <h2 id="description-heading">Describe your HI scenario</h2>
  <p class="hint">Answer in your own words. You can skip any question.</p>

  <div class="progress">
    <p class="hint" id="scenario-wizard-position">Section {step + 1} of {questions.length}</p>
    <progress aria-label="Current description section" value={step + 1} max={questions.length}></progress>
  </div>

  <h3 tabindex="-1" aria-describedby="scenario-wizard-position" bind:this={heading}>{question.title}</h3>
  <p id="scenario-wizard-prompt">{question.prompt}</p>
  <label class="sr-only" for="scenario-wizard-answer">Your description</label>
  <textarea
    id="scenario-wizard-answer"
    aria-describedby="scenario-wizard-prompt"
    rows="6"
    value={answers[question.id] ?? ''}
    oninput={(event) => onAnswer(question.id, event.currentTarget.value)}
  ></textarea>

  <div class="toolbar navigation">
    <button type="button" onclick={() => move(-1)} disabled={step === 0}>Previous</button>
    <button type="button" onclick={() => move(1)} disabled={step === questions.length - 1}>Next</button>
  </div>

  <details>
    <summary>View full description</summary>
    {#if answeredQuestions.length}
      <dl class="description">
        {#each answeredQuestions as { id, title } (id)}
          <dt>{title}</dt>
          <dd>{answers[id]}</dd>
        {/each}
      </dl>
    {:else}
      <p class="hint">Your answers will appear here.</p>
    {/if}
  </details>

  <div class="conversion">
    <button type="button" class="primary" onclick={onInterpret} disabled={!answeredQuestions.length || interpreting}>Convert to JSON using AI</button>
    <p class="hint">Converting sends your full description to VU Nebula. Review the generated candidate before using it.</p>
    {#if interpreting}<p class="status" role="status">Interpreting description…</p>{/if}
    <div class="toolbar">
      <button type="button" onclick={() => onLoadExample('complete')}>Load complete description</button>
      <button type="button" onclick={() => onLoadExample('incomplete')}>Load incomplete description</button>
    </div>
  </div>
</section>

<style>
  .wizard {
    padding: 1rem 1.25rem;
    background: #fff;
    border: 1px solid var(--border);
    border-radius: 6px;
  }

  .progress {
    margin: 1rem 0;
  }

  progress {
    display: block;
    width: 100%;
    accent-color: var(--accent);
  }

  #scenario-wizard-prompt {
    margin: 0.35rem 0 0.6rem;
  }

  textarea {
    display: block;
    resize: vertical;
  }

  .navigation {
    justify-content: space-between;
    margin-bottom: 1rem;
  }

  .description dt {
    font-weight: 600;
  }

  .description dd {
    margin: 0 0 0.75rem;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  .conversion {
    margin-top: 1rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border);
  }
</style>
