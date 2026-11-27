// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';
import ResearcherFeedback from './ResearcherFeedback.svelte';

/** @type {Record<string, any> | undefined} */
let component;
afterEach(async () => {
  if (component) await unmount(component);
  component = undefined;
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
});

/** @param {string} message */
function enter(message) {
  const input = /** @type {HTMLTextAreaElement} */ (document.getElementById('feedback-message'));
  input.value = message;
  input.dispatchEvent(new Event('input', { bubbles: true }));
  flushSync();
  return input;
}

function submit() {
  document.querySelector('form')?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  flushSync();
}

it('sends only explicit feedback, prevents duplicate pending submissions, and confirms storage', async () => {
  /** @type {(response: Response) => void} */
  let complete = (_response) => { throw new Error('No pending submission'); };
  const fetch = vi.fn((/** @type {string} */ _url, /** @type {RequestInit} */ _options) => new Promise((resolve) => { complete = resolve; }));
  vi.stubGlobal('fetch', fetch);
  component = mount(ResearcherFeedback, { target: document.body });
  flushSync();
  const message = enter('Synthetic feedback about the prototype.');
  submit();
  submit();
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls[0]?.[0]).toMatch(/\/feedback$/);
  const options = /** @type {RequestInit} */ (fetch.mock.calls[0]?.[1]);
  expect(JSON.parse(String(options.body))).toEqual({
    category: 'problem', area: 'general', message: 'Synthetic feedback about the prototype.',
  });
  expect(document.querySelector('fieldset')?.disabled).toBe(true);
  complete(new Response(JSON.stringify({ id: 'feedback-reference', created_at: '2026-11-27T12:00:00Z' }), { status: 201 }));
  await vi.waitFor(() => { flushSync(); expect(document.querySelector('[role=status]')?.textContent).toContain('feedback-reference'); });
  expect(message.value).toBe('');
  expect(document.querySelector('fieldset')?.disabled).toBe(false);
});

it('retains the message on failure and displays no raw server diagnostics', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ private: 'RAW_PRIVATE_SERVER_DIAGNOSTIC' }), { status: 503 })));
  component = mount(ResearcherFeedback, { target: document.body });
  flushSync();
  const message = enter('Synthetic unsent observation.');
  submit();
  await vi.waitFor(() => { flushSync(); expect(document.querySelector('[role=alert]')?.textContent).toContain('could not be confirmed'); });
  expect(message.value).toBe('Synthetic unsent observation.');
  expect(document.body.textContent).not.toContain('RAW_PRIVATE_SERVER_DIAGNOSTIC');
});

it('does not send an empty message and labels privacy and length limits', () => {
  const fetch = vi.fn();
  vi.stubGlobal('fetch', fetch);
  component = mount(ResearcherFeedback, { target: document.body });
  flushSync();
  const input = enter('  \n ');
  submit();
  expect(fetch).not.toHaveBeenCalled();
  expect(input.maxLength).toBe(6000);
  expect(input.required).toBe(true);
  expect(document.body.textContent).toContain('Scenario contents and browser details are not attached');
  expect(document.querySelector('label[for=feedback-message]')).not.toBeNull();
});
