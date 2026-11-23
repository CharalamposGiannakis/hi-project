// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import { questions } from './interpretation.js';
import ScenarioWizard from './ScenarioWizard.svelte';

/** @type {ReturnType<typeof mount> | undefined} */
let wizard;
afterEach(async () => {
  if (wizard) await unmount(wizard);
  wizard = undefined;
  document.body.innerHTML = '';
});

/** @param {string} label */
function button(label) {
  const control = [...document.querySelectorAll('button')].find((element) => element.textContent?.trim() === label);
  if (!control) throw new Error(`Missing button ${label}`);
  return control;
}

function render() {
  const answers = $state(/** @type {import('./interpretation.js').Answers} */ ({}));
  const onInterpret = vi.fn();
  wizard = mount(ScenarioWizard, {
    target: document.body,
    props: {
      answers,
      onAnswer: (id, value) => { answers[id] = value; },
      onInterpret,
    },
  });
  flushSync();
  return { answers, onInterpret };
}

/** @param {string} id */
function textareaById(id) {
  const element = document.getElementById(id);
  if (!(element instanceof HTMLTextAreaElement)) throw new Error(`Missing textarea ${id}`);
  return element;
}

/** @param {HTMLTextAreaElement} textarea @param {string} value */
function enter(textarea, value) {
  textarea.value = value;
  textarea.dispatchEvent(new Event('input', { bubbles: true }));
  flushSync();
}

it('skips unanswered sections, retains raw answers, and shows notes in the full description', async () => {
  const { answers, onInterpret } = render();
  const textarea = textareaById('scenario-wizard-answer');
  const progress = /** @type {HTMLProgressElement} */ (document.querySelector('progress'));
  expect(button('Previous').disabled).toBe(true);
  expect(button('Convert to JSON using AI').disabled).toBe(true);
  expect(progress.value).toBe(1);

  const description = '  A person and a robot work together.\nMore details to follow.  ';
  enter(textarea, description);
  expect(answers.use_case).toBe(description);
  for (let index = 1; index < questions.length; index++) {
    button('Next').click();
    flushSync();
  }
  await tick();
  expect(document.activeElement?.textContent).toMatch(/additional notes/i);
  expect(progress.value).toBe(questions.length);
  expect(textarea.value).toBe('');
  expect(button('Next').disabled).toBe(true);

  enter(textarea, 'Team roles are still under discussion.');
  document.querySelector('summary')?.click();
  const fullDescription = document.querySelector('details');
  expect(fullDescription?.open).toBe(true);
  expect([...fullDescription?.querySelectorAll('dd') ?? []].map((answer) => answer.textContent)).toEqual([
    description, 'Team roles are still under discussion.',
  ]);

  for (let index = 1; index < questions.length; index++) {
    button('Previous').click();
    flushSync();
  }
  expect(textarea.value).toBe(description);
  button('Convert to JSON using AI').click();
  expect(onInterpret).toHaveBeenCalledOnce();
});

it('opens distinct blank editors, keeps both values and returns to the same question', async () => {
  const { answers } = render();
  button('Next').click();
  await tick();
  const fullDescription = '  A human and an AI plan a route.\nThe human checks the plan.  ';
  const notes = '  How do they handle uncertain routes?\nStill open.  ';

  button('Write full description').click();
  await tick();
  const fullEditor = textareaById('scenario-full-description');
  expect(document.activeElement).toBe(fullEditor);
  expect(fullEditor.value).toBe('');
  expect(button('Convert to JSON using AI').disabled).toBe(true);
  enter(fullEditor, fullDescription);
  expect(button('Convert to JSON using AI').disabled).toBe(false);

  button('Add additional notes').click();
  await tick();
  const notesEditor = textareaById('scenario-additional-notes');
  expect(document.activeElement).toBe(notesEditor);
  expect(notesEditor.value).toBe('');
  enter(notesEditor, notes);

  button('Back to questions').click();
  await tick();
  expect(document.activeElement?.textContent).toBe('Goal');
  const goal = 'Plan a safe route.';
  enter(textareaById('scenario-wizard-answer'), goal);
  expect(answers).toEqual({ full_description: fullDescription, additional_notes: notes, goal });

  button('Write full description').click();
  await tick();
  expect(textareaById('scenario-full-description').value).toBe(fullDescription);
  button('Add additional notes').click();
  await tick();
  expect(textareaById('scenario-additional-notes').value).toBe(notes);

  document.querySelector('summary')?.click();
  expect([...document.querySelectorAll('.description dd')].map((answer) => answer.textContent)).toEqual([fullDescription, goal, notes]);
});
