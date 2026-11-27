/** @typedef {'home' | 'builder' | 'management' | 'explorer' | 'feedback'} ViewId */

/** @type {{ id: ViewId, label: string, heading: string, description: string, status?: string }[]} */
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
  },
  {
    id: 'management',
    label: 'Scientific Knowledge Management',
    heading: 'Scientific Knowledge Management',
    description: 'Scientific review and publication management are planned for the next phase. This area will support reviewing submissions and managing approved knowledge.',
    status: 'Planned',
  },
  {
    id: 'explorer',
    label: 'Knowledge Explorer',
    heading: 'HI Knowledge Explorer',
    description: 'Query validated session scenarios and shared knowledge, inspect supporting RDF evidence, and compare recorded HINT concepts across scenarios.',
  },
  {
    id: 'feedback',
    label: 'Researcher feedback',
    heading: 'Researcher feedback',
    description: 'Share feedback for restricted manual review by the project operator.',
  },
];
