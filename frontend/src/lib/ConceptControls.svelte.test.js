// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';
import ConceptSelect from './ConceptSelect.svelte';
import ConceptChecklist from './ConceptChecklist.svelte';
import { findConcept } from './scenario.js';

/** @type {Record<string, any> | undefined} */
let component;
afterEach(async () => {
  if (component) await unmount(component);
  component = undefined;
  document.body.innerHTML = '';
});

describe('vocabulary controls', () => {
  it('simplifies options, keeps semantic values, and discloses canonical details on demand', () => {
    const props = $state({ label: 'Domain', category: /** @type {const} */ ('Domain'), value: 'EducationDomain' });
    component = mount(ConceptSelect, { target: document.body, props });
    flushSync();
    const select = /** @type {HTMLSelectElement} */ (document.querySelector('select'));
    expect(select.selectedOptions[0].textContent).toBe('Education');
    expect(select.value).toBe('EducationDomain');
    const help = /** @type {HTMLDetailsElement} */ (document.querySelector('details'));
    expect(help.open).toBe(false);
    expect(help.textContent).toContain('Education Domain');
    expect(help.textContent).toContain('hint:EducationDomain');
    expect(help.textContent).toContain(findConcept('Domain', 'EducationDomain')?.definition);
    help.querySelector('summary')?.click();
    expect(help.open).toBe(true);
    select.value = 'DigitalMuseumDomain';
    select.dispatchEvent(new Event('change', { bubbles: true }));
    flushSync();
    expect(props.value).toBe('DigitalMuseumDomain');
    expect(select.selectedOptions[0].textContent).toBe('Digital Museum');
    expect(help.textContent).toContain('hint:DigitalMuseumDomain');
  });

  it('keeps checkbox IDs and definitions for selected and unselected concepts', () => {
    const props = $state({ label: 'Roles', category: /** @type {const} */ ('Role'), values: ['HumanUserRole'] });
    component = mount(ConceptChecklist, { target: document.body, props });
    flushSync();
    const label = [...document.querySelectorAll('label')].find((label) => label.textContent?.trim() === 'Clinician');
    const checkbox = /** @type {HTMLInputElement} */ (label?.querySelector('input'));
    expect(checkbox.value).toBe('ClinicianRole');
    expect(checkbox.checked).toBe(false);
    const help = /** @type {HTMLDetailsElement} */ (document.querySelector('details'));
    expect(help.open).toBe(false);
    expect(help.textContent).toContain(findConcept('Role', 'ClinicianRole')?.definition);
    expect(help.textContent).toContain('hint:HumanUserRole');
    checkbox.click();
    flushSync();
    expect(props.values).toEqual(['HumanUserRole', 'ClinicianRole']);
    expect(help.open).toBe(false);
  });
});
