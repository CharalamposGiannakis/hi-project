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

it('skips unanswered sections, retains raw answers, and shows notes in the full description', async () => {
  const answers = $state(/** @type {import('./interpretation.js').Answers} */ ({}));
  const onInterpret = vi.fn();
  wizard = mount(ScenarioWizard, {
    target: document.body,
    props: {
      answers,
      onAnswer: (id, value) => { answers[id] = value; },
      onInterpret,
      onLoadExample: vi.fn(),
    },
  });
  flushSync();

  const textarea = /** @type {HTMLTextAreaElement} */ (document.getElementById('scenario-wizard-answer'));
  const progress = /** @type {HTMLProgressElement} */ (document.querySelector('progress'));
  expect(button('Previous').disabled).toBe(true);
  expect(button('Convert to JSON using AI').disabled).toBe(true);
  expect(progress.value).toBe(1);

  const description = '  A person and a robot work together.\nMore details to follow.  ';
  textarea.value = description;
  textarea.dispatchEvent(new Event('input', { bubbles: true }));
  flushSync();
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

  textarea.value = 'Team roles are still under discussion.';
  textarea.dispatchEvent(new Event('input', { bubbles: true }));
  flushSync();
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
