<script>
  import { onDestroy } from 'svelte';
  import { issuePath, requestPreview } from './api.js';
  import { readInterpretationDocument } from './interpretation.js';

  /** @type {{ uploads?: import('./api.js').SessionUpload[] }} */
  let { uploads = $bindable([]) } = $props();
  let loading = $state(false);
  let failures = $state(/** @type {{ file: string, message: string, fields: string[], report?: string | null }[]} */ ([]));
  const controller = new AbortController();
  onDestroy(() => controller.abort());

  /** @param {Event} event */
  async function addFiles(event) {
    if (!(event.currentTarget instanceof HTMLInputElement)) return;
    const input = event.currentTarget;
    const files = [...(input.files ?? [])];
    if (!files.length) return;
    loading = true;
    failures = [];
    for (const file of files) {
      try {
        const parsed = JSON.parse(await file.text());
        const document = readInterpretationDocument(parsed);
        const scenario = document ? document.scenario : parsed;
        if (!scenario || typeof scenario !== 'object' || Array.isArray(scenario)) {
          throw new Error('This file has no scenario candidate. Complete the scenario in the Builder first.');
        }
        const result = await requestPreview(scenario, { signal: controller.signal });
        if (controller.signal.aborted) return;
        if (result.kind === 'ok') {
          uploads = [...uploads, { id: 'upload-' + crypto.randomUUID(), file_name: file.name, scenario, selected: true }];
        } else if (result.kind === 'rejected') {
          failures.push({
            file: file.name, message: result.error.message,
            fields: result.error.issues.map((issue) => `${issuePath(issue.location)} — ${issue.message}`),
            report: result.error.shacl_report,
          });
        } else {
          failures.push({ file: file.name, message: 'Technical validation could not be completed. Try uploading this file again.', fields: [] });
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        failures.push({
          file: file.name,
          message: error instanceof SyntaxError ? 'This file is not valid JSON.'
            : error instanceof Error ? error.message : 'This file could not be read.',
          fields: [],
        });
      }
    }
    loading = false;
    input.value = '';
  }

  /** @param {string} id */
  function removeUpload(id) {
    uploads = uploads.filter((upload) => upload.id !== id);
  }

  /** @param {import('./api.js').SessionUpload} upload */
  function scenarioSummary(upload) {
    const scenario = /** @type {Record<string, any>} */ (upload.scenario);
    return `${scenario.use_case?.name ?? 'Scenario'} (${scenario.id ?? ''})`;
  }
</script>

<section class="uploads" aria-labelledby="uploads-heading">
  <h2 id="uploads-heading">Experimental scenarios</h2>
  <p class="hint">Add validated Builder scenarios or upload canonical JSON and draft exports. These scenarios stay provisional in this browser session. Select the scenarios to include in queries.</p>
  <label class="button file-button">Upload scenario files
    <input id="explorer-upload-files" type="file" accept=".json,application/json" multiple disabled={loading} onchange={addFiles} />
  </label>
  {#if loading}<p role="status">Validating uploaded scenarios…</p>{/if}
  {#each failures as failure}
    <div class="error" role="alert">
      <strong>{failure.file}</strong> — {failure.message}
      {#if failure.fields.length}<ul>{#each failure.fields as field}<li>{field}</li>{/each}</ul>{/if}
      {#if failure.report}<details><summary>Technical validation details</summary><pre>{failure.report}</pre></details>{/if}
    </div>
  {/each}
  {#if uploads.length}
    <ul>
      {#each uploads as upload (upload.id)}
        <li>
          <label class="inline"><input type="checkbox" bind:checked={upload.selected} aria-label="Include {upload.file_name}" />
            {upload.file_name} · {scenarioSummary(upload)} · Provisional session scenario
          </label>
          <button class="link" type="button" aria-label="Remove {upload.file_name}" onclick={() => removeUpload(upload.id)}>Remove</button>
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .uploads { display: grid; gap: 0.75rem; margin: 1rem 0; padding: 1rem 1.25rem; border: 1px solid var(--border); border-radius: 6px; background: #fff; }
  h2, .hint { margin: 0; }
  .file-button { display: inline-flex; justify-self: start; align-items: center; }
  ul { margin: 0; padding-left: 1.25rem; }
  li { margin-top: 0.5rem; overflow-wrap: anywhere; }
  pre { white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
