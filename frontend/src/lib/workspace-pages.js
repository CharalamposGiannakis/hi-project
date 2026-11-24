/** @typedef {'home' | 'builder' | 'management' | 'explorer'} ViewId */

/** @type {{ id: ViewId, label: string, heading: string, description: string, action?: string, status?: string }[]} */
export const workspacePages = [
  {
    id: 'home',
    label: 'Home',
    heading: 'Home',
    description: 'Describe, validate, and explore Hybrid Intelligence research scenarios.',
  },
  {
    id: 'builder',
    label: 'Scenario Builder',
    heading: 'HI Scenario Builder',
    description: 'Describe a scenario with guided questions or AI assistance, refine its structured representation, and validate its RDF. Add a validated snapshot to the Explorer when ready.',
    action: 'Open Scenario Builder',
  },
  {
    id: 'management',
    label: 'Scientific Knowledge Management',
    heading: 'Scientific Knowledge Management',
    description: 'Scientific review and publication management are planned for the next implementation phase. This area will support reviewing scenario submissions and managing approved knowledge.',
    action: 'View planned review',
    status: 'Planned',
  },
  {
    id: 'explorer',
    label: 'Knowledge Explorer',
    heading: 'HI Knowledge Explorer',
    description: 'Query validated session scenarios and shared knowledge, inspect supporting RDF evidence, and compare recorded HINT concepts across scenarios.',
    action: 'Open Knowledge Explorer',
  },
];
