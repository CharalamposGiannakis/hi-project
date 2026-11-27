<script>
  import { submitFeedback } from './api.js';

  let category = $state('problem');
  let area = $state('general');
  let message = $state('');
  let pending = $state(false);
  let error = $state('');
  let receipt = $state('');

  async function send() {
    if (pending) return;
    error = '';
    receipt = '';
    if (!message.trim()) {
      error = 'Enter a message before sending feedback.';
      return;
    }
    pending = true;
    const result = await submitFeedback({ category, area, message });
    pending = false;
    if (result.kind === 'ok') {
      receipt = result.data.id;
      message = '';
    } else {
      // Keep the researcher's text and avoid showing raw server diagnostics.
      error = 'Feedback could not be confirmed as saved. Your message is still here; try again when the service is available.';
    }
  }
</script>

<div class="feedback-form">
  <p>Report a problem, suggest an improvement, or share a scientific observation. The project operator reviews submissions manually. Feedback is separate from scenario submissions and scientific approval.</p>
  <p id="feedback-privacy" class="hint">Feedback contains only the fields below. Scenario contents and browser details are not attached. Avoid credentials, personal information, and confidential research data.</p>

  <form onsubmit={(event) => { event.preventDefault(); void send(); }} aria-describedby="feedback-privacy" aria-busy={pending}>
    <fieldset disabled={pending}>
      <legend>Your feedback</legend>
      <div class="field">
        <label for="feedback-category">Feedback type</label>
        <select id="feedback-category" bind:value={category}>
          <option value="problem">Report a problem</option>
          <option value="improvement">Suggest an improvement</option>
          <option value="scientific_observation">Scientific observation</option>
        </select>
      </div>
      <div class="field">
        <label for="feedback-area">Application area</label>
        <select id="feedback-area" bind:value={area}>
          <option value="general">General</option>
          <option value="home">Home</option>
          <option value="builder">Scenario Builder</option>
          <option value="management">Scientific Knowledge Management</option>
          <option value="explorer">Knowledge Explorer</option>
        </select>
      </div>
      <div class="field">
        <label for="feedback-message">Message</label>
        <textarea id="feedback-message" bind:value={message} rows="8" maxlength="6000" required aria-describedby="feedback-length"></textarea>
        <p id="feedback-length" class="hint">Up to 6000 characters. Include enough detail for the operator to understand your observation.</p>
      </div>
      <button class="primary" type="submit">{pending ? 'Sending feedback…' : 'Send feedback'}</button>
    </fieldset>
  </form>
  {#if receipt}<p role="status" class="ok">Feedback saved for manual review. Reference: <code>{receipt}</code></p>{/if}
  {#if error}<p role="alert" class="error">{error}</p>{/if}
  <p class="hint">Unsent feedback stays here while you navigate. Closing or reloading the app clears unsent text. Feedback is not an urgent support channel.</p>
</div>

<style>
  .feedback-form { max-width: 48rem; }
  form { margin-top: 1rem; }
  textarea { resize: vertical; min-height: 10rem; }
  code { overflow-wrap: anywhere; }
</style>
