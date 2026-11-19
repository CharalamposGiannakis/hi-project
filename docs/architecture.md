# Architecture

This document briefly describes the HI system's architecture, current implementation, and planned development. The goal is to provide a clear overview of how the components fit together and how the project is progressing.

#### Stakeholders

1. **Researchers and technical reviewers:** Researchers from different disciplines contribute HI scenarios; technical reviewers assess the system and provide engineering feedback.
2. **Scientific Authority (Ilaria):** Maintains the scientific meaning and consistency of the shared knowledge graph and approves published scenarios.
3. **Engineers (Babis):** Build, operate, and evolve the system while respecting scientific decisions.

#### Current System

The Svelte Builder supports guided description and structured scenario entry using HINT concepts. FastAPI validates scenario JSON, generates RDF, and checks SHACL constraints. The backend also provides GraphDB storage and team-composition exploration (CQ1).

## Three Architectural Pillars

The pillars can be developed independently but share one scenario representation and validation pipeline.

### Pillar 1 — Scenario Builder with LLM Assistance

Researchers create, inspect, edit, validate, and eventually submit HI scenarios for scientific review.

**Phase 1A — Generate or regenerate**

The wizard sends the full description to FastAPI for interpretation by Nebula. Each request includes the Python `Scenario` schema and all approved HINT concepts from the checked-in thesaurus. The backend checks the proposal and retains supported fields in a canonical-shaped draft even when required facts are missing. The interpretation document records the source sent, proposed candidate, findings, model, and prompt version alongside the current editable fields. Explicit technical validation sends only the edited candidate through the existing RDF and SHACL pipeline.

```text
┌─────────────────────────────────────────────────────────┐
│                  HI Scenario Builder                    │
├────────────────────────────────┬────────────────────────┤
│                                │                        │
│  Describe your HI scenario     │     Scenario JSON      │
│                                │                        │
│  ● ● ● ○ ○ ○ ○ ○ ○ ○ ○         │ {                      │
│  3 of 12 sections              │    "scenario": {       │
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

- **Input:** HIDe-inspired wizard with optional natural-language questions, progress indicators, Previous/Next navigation, and an Additional Notes section.
- **Live JSON:** Answers immediately update the source-description portion of the JSON preview without requiring LLM interpretation.
- **AI interpretation:** **Convert to JSON using AI** processes the complete description and produces structured scenario JSON, unresolved issues, and semantic suggestions.
- **Structured editing:** The generated JSON populates the existing dropdown editor. Researchers can add, remove, and correct elements; the JSON updates automatically.
- **JSON viewer:** Preserve the right-side preview, **Open JSON in new tab**, and JSON download.
- **Regeneration:** Researchers can modify their descriptions and regenerate the scenario. Existing manual corrections must not be overwritten without confirmation.
- **Validation:** Keep technical validation and RDF preview in the Scenario Builder. Incomplete or unsupported information must be reported rather than invented.
- **Submission:** A future **Submit for Scientific Review** action will transfer the scenario to Pillar 2. Phase 1A does not automatically publish to GraphDB.

**Phase 1B — Deferred**

Natural-language modifications to selected parts of an existing JSON scenario. Consider only if researchers need this functionality.

### Pillar 2 — Scientific Authority Workspace

**Planned.**

- Receive submissions from the Scenario Builder.
- Review scenarios, original descriptions, unresolved issues, and semantic suggestions.
- Correct, approve, reject, and publish scenarios.
- Preserve scenario revisions and scientific decisions.
- Publish approved scenarios to GraphDB.

**Open architectural decision — Persistence**

Two alternatives are under consideration:

1. **SQLite + GraphDB:** SQLite manages drafts, submissions, and reviews; GraphDB stores scenario knowledge.
2. **GraphDB only:** Named graphs store scenarios and workflow metadata. A separate workflow vocabulary represents submissions, descriptions, issues, revisions, and scientific decisions. Original JSON can be preserved as an RDF literal.

The decision remains open pending a small implementation experiment.

### Pillar 3 — Query & Exploration

**Partially implemented.**

- SPARQL queries and competency questions (CQ1 currently implemented).
- Explore approved scenarios or selected combinations of approved and provisional scenarios.
- Use named graphs to distinguish experimental knowledge from scientifically approved knowledge.
- Provide readable query results and potentially LLM-generated explanations grounded in retrieved data.

## Notes

- Technical validation does not constitute scientific approval.
- Experimental scenarios must remain distinguishable from approved knowledge.
- The three pillars share one scenario representation and validation pipeline.
- GraphDB is the existing knowledge-graph database; the workflow persistence approach remains undecided.


