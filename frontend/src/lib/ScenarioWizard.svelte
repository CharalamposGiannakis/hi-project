<script>
  import { tick } from 'svelte';
  import { descriptionFields, questions } from './interpretation.js';

  /** @typedef {import('./interpretation.js').Answers} Answers */
  /** @type {{
   *   answers: Answers,
   *   onAnswer: (id: import('./interpretation.js').AnswerId, value: string) => void,
   *   onInterpret: () => void,
   *   interpreting?: boolean,
   * }} */
  let { answers, onAnswer, onInterpret, interpreting = false } = $props();

  const textEditors = {
    full_description: { inputId: 'scenario-full-description', label: 'Full description' },
    additional_notes: { inputId: 'scenario-additional-notes', label: 'Additional notes' },
  };
  let activeEditor = $state(/** @type {keyof typeof textEditors | null} */ (null));
  let textEditor = $state(/** @type {HTMLTextAreaElement | undefined} */ (undefined));

  let step = $state(0);
  let heading = $state(/** @type {HTMLHeadingElement | undefined} */ (undefined));
  let question = $derived(questions[step]);
  let writtenFields = $derived(descriptionFields.filter(({ id }) => answers[id]?.trim()));

  /** @param {keyof typeof textEditors} id */
  async function openEditor(id) {
    activeEditor = id;
    await tick();
    textEditor?.focus();
  }

  async function returnToQuestions() {
    activeEditor = null;
    await tick();
    heading?.focus();
  }

  /** @param {number} offset */
  async function move(offset) {
    step += offset;
    await tick();
    heading?.focus();
  }
</script>

<section class="wizard" aria-labelledby="description-heading">
  <h2 id="description-heading">Describe your HI scenario</h2>
  <p class="hint">Write a full description or answer any of the questions in your own words.</p>

  <div class="toolbar" role="group" aria-label="Description input options">
    <button type="button" onclick={() => openEditor('full_description')}>Write full description</button>
    <button type="button" onclick={() => openEditor('additional_notes')}>Add additional notes</button>
    {#if activeEditor}<button type="button" onclick={returnToQuestions}>Back to questions</button>{/if}
  </div>

  {#if activeEditor}
    {@const answerId = activeEditor}
    {@const editor = textEditors[answerId]}
    {#key answerId}
      <div class="free-text">
        <label class="label" for={editor.inputId}>{editor.label}</label>
        <textarea
          id={editor.inputId}
          rows="8"
          bind:this={textEditor}
          value={answers[answerId] ?? ''}
          oninput={(event) => onAnswer(answerId, event.currentTarget.value)}
        ></textarea>
      </div>
    {/key}
  {:else}
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
  {/if}

  <details>
    <summary>View full description</summary>
    {#if writtenFields.length}
      <dl class="description">
        {#each writtenFields as { id, title } (id)}
          <dt>{title}</dt>
          <dd>{answers[id]}</dd>
        {/each}
      </dl>
    {:else}
      <p class="hint">Your answers will appear here.</p>
    {/if}
  </details>

  <div class="conversion">
    <button type="button" class="primary" onclick={onInterpret} disabled={!writtenFields.length || interpreting}>Convert to JSON using AI</button>
    <p class="hint">Converting sends all description text and notes to VU Nebula. Review the generated candidate before using it.</p>
    {#if interpreting}<p class="status" role="status">Interpreting description…</p>{/if}
  </div>
</section>

<style>
  .wizard {
    padding: 1rem 1.25rem;
    background: #fff;
    border: 1px solid var(--border);
    border-radius: 6px;
  }

  .progress, .free-text {
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
