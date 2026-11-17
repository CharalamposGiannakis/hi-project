# Architecture

This document briefly describes the HI system's architecture, current implementation, and planned development. The goal is to provide a clear overview of how the components fit together and how the project is progressing.

#### Stakeholders

1. **Researchers and technical reviewers:** Researchers from different disciplines contribute HI scenarios; technical reviewers assess the system and provide engineering feedback.
2. **Scientific Authority (Ilaria):** Maintains the scientific meaning and consistency of the shared knowledge graph and approves published scenarios.
3. **Engineers (Babis):** Build, operate, and evolve the system while respecting scientific decisions.

#### Current System

The existing Svelte editor supports structured scenario entry using HINT concepts. FastAPI validates scenario JSON, generates RDF, checks SHACL constraints, and stores scenarios in GraphDB. The application currently supports team-composition exploration (CQ1).

## Three Architectural Pillars

The pillars can be developed independently but share one scenario representation and validation pipeline.

### Pillar 1 — Scenario Builder with LLM Assistance

Researchers create, inspect, and edit HI scenarios.

**Phase 1A — Generate or regenerate**

A HIDe-inspired, `step-by-step guided form collects optional natural-language answers, including free-form notes`. Researchers can navigate between questions and review the full description. Answers appear immediately as source text in the JSON preview. A **Convert to JSON using AI** action generates a candidate structured scenario and records interpretation issues and suggestions in one JSON document. The existing editor is populated from the candidate, allowing researchers to add, remove, or correct elements. The JSON preview and **Open JSON in new tab** remain available. The existing validation pipeline verifies the structured scenario; no automatic publication occurs.

```text
┌─────────────────────────────────────────────────────────┐
│                  HI Scenario Builder                    │
├────────────────────────────────┬────────────────────────┤
│                                │                        │
│  Describe your HI scenario     │     Scenario JSON      │
│                                │                        │
│  ● ● ● ○ ○ ○ ○ ○ ○ ○ ○         │ {                      │
│  3 of 11 sections              │    "scenario": {       │
│                                │      ...               │
│  ───────────────────────────   │    }                   │
│                                │  }                     │
│  Agent Capabilities            │                        │
│                                │                        │
│  What can each agent do?       │                        │
│  Which tasks can they perform? │                        │
│                                │                        │
│  ┌──────────────────────────┐  │                        │
│  │                          │  │                        │
│  │ Your description...      │  │                        │
│  │                          │  │                        │
│  └──────────────────────────┘  │                        │
│                                │                        │
│  [Previous]        [Next]      │                        │
│                                │                        │
│  [View full description]       │                        │
│                                │                        │
│  [Convert to JSON using AI]    │                        │
└────────────────────────────────┴────────────────────────┘
```

**Phase 1B — Modify existing JSON**

The researcher writes exactly the same sentence:

"The AI assistant also analyzes medical images."

But this time, the LLM receives the current JSON and the new instruction.

It proposes adding the relevant capability to the existing AI agent, without modifying unrelated information.

The researcher accepts the change, and the JSON updates.

### Pillar 2 — Scientific Authority Workspace

**Planned.** A dedicated interface for scientific review, correction, and approval. SQLite will preserve submissions, drafts, suggestions, and review decisions. Approved scenarios will be published to GraphDB; named graphs can also support provisional exploration without mixing it with approved knowledge.

### Pillar 3 — Query & Exploration

**Partially implemented.** GraphDB executes SPARQL queries; CQ1 is currently available. Planned extensions include additional supported competency questions, readable query results, and optional LLM explanations grounded in retrieved knowledge.

## Notes

