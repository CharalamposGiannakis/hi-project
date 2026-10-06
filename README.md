# HI Knowledge Graph Population Interface

## Status

Early research prototype. All design, architecture, stack, and interaction choices are **provisional** and should evolve as the project becomes clearer.

---

## Design Problem

> **How can a researcher describe an HI scenario without having to think like an ontology engineer, while still knowing and controlling what the machine is adding to the shared knowledge graph?**

Target users are **Hybrid Intelligence researchers**. The immediate goal is to make populating the HI Knowledge Graph understandable, interactive, and visually convincing.

---

## Initial Architecture

Two input channels should lead to the **same structured representation**.

```text
                         ┌── Manual structured input
                         │   Sidebar form / JSON editor
Researcher ──────────────┤
                         │
                         └── LLM-assisted description
                                   │
                                   ▼
                         Proposed form values
                                   │
                            Human review/edit
                                   │
                 ┌─────────────────┴─────────────────┐
                 │                                   │
                 │     interaction data recorded     │
                 │  accepted / edited / rejected     │
                 │                                   │
                 └─────────────────┬─────────────────┘
                                   │
                                   ▼
                         Canonical Scenario JSON
                                   │
                          validate / correct
                                   │
                                   ▼
                              JSON → RDF
                                   │
                                SHACL
                                   │
                                   ▼
                            Preview ABox
                                   │
                          Researcher approves
                                   │
                                   ▼
                               GraphDB
                          ┌────────┴────────┐
                          ▼                 ▼
                    SPARQL / query    GraphDB visualisation
                          │
                          ▼
                    Application UI
                          │
                          ▼
                  Own graph visualisation
```

The LLM should `propose values for the same structure used by manual entry`, rather than creating a separate data path.

Human review should remain explicit before anything is committed to the graph.

---

## Interaction Research

The LLM channel can also produce useful interaction data.

For each proposed entry, record whether the researcher:

- accepted it unchanged,
- edited it before accepting,
- rejected it.

This can later support metrics such as **LLM acceptance rate**, correction rate, and acceptance percentage per ontology field or concept.

---

## Graph Interaction

GraphDB can remain directly accessible for researchers who want advanced graph exploration or SPARQL querying.

The application should also provide its own graph visualisation, designed around the current task rather than trying to reproduce all GraphDB functionality.

---

## Suggested Stack

```text
Frontend        Svelte / SvelteKit
Backend         Python + FastAPI
Knowledge Graph GraphDB
Semantic layer  RDF / OWL / SHACL
AI              LLM-assisted structured extraction
```

This is the current preferred direction, not a locked technical decision.

---

## First Deliverables

```text
ontology_map.md
scenario_01_source.ttl
scenario_01.json
json_schema.json
json_to_rdf.py
validation.py
README.md
```

- **ontology_map.md**
Minimal working map of the HI Ontology: important classes, relationships, HINT concepts, validation requirements, and what the UI eventually needs to collect.

- **scenario_01_source.ttl**
One existing valid HI scenario taken from the current knowledge graph and used as the reference case.

- **scenario_01.json**
Human-oriented JSON representation of the same scenario.

- **json_schema.json**
Definition of the canonical structured representation expected from both manual and LLM-assisted input.

- **json_to_rdf.py**
Deterministic conversion from canonical JSON into an HI Ontology ABox.

- **validation.py**
Validation pipeline for generated RDF, initially using the existing SHACL shapes.

- **README.md**
Living notebook of the current project state, decisions, architecture, and next steps.

---

## Next Steps - Current Priority

- **Understand the ontology and one existing scenario** \
Map the relevant ontology structure and reverse-engineer one complete scenario from the existing KG. \
**Goal**: understand exactly what information must be collected from a researcher.


- **Define and validate the canonical JSON representation** \
Represent the selected scenario as JSON and build: \
`JSON → RDF → SHACL validation` \
**Goal**: reproduce a valid ABox without depending on any UI or LLM.

- **Design the researcher interaction** \
Once the required information is understood, design the manual form, LLM-assisted filling, review interaction, ABox preview, and graph visualisation. \
**Goal**: produce one strong end-to-end vertical slice before expanding the system.

---

## MVP Principle

`Build one complete scenario well before supporting the whole ontology.`

The first milestone is not a production system. It is a convincing researcher-facing prototype that demonstrates how the HI Knowledge Graph can grow through understandable and controlled human interaction.