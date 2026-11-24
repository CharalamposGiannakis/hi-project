# Architecture

Three pillars share one canonical `Scenario` JSON model and one technical validation pipeline. See the [README](../README.md) for the current workflow and API.

## Roles

- **Researchers** contribute scenarios from their domains. Technical reviewers provide engineering feedback.
- **Scientific Authority (Ilaria)** stewards the shared knowledge graph and makes scientific decisions.
- **Engineering (Babis)** builds, operates, and maintains the system.

## Pillar 1 — Scenario Builder with LLM Assistance

**Implemented · Phase 1A**

- The full-description editor, guided questions, additional notes, and structured editor share a draft. Researchers can correct HINT-backed fields and preview, export, or reopen incomplete drafts.
- On request, FastAPI sends the full description to VU Nebula with the `Scenario` schema and approved HINT vocabulary. The prompt asks Nebula to inventory entities before classifying them, so partial proposals can retain stated details and links even when HINT mappings are unresolved.
- The draft keeps the source sent to Nebula, generated proposal, findings, model, prompt version, and SHA-256 of the effective system prompt alongside the editable candidate. Researchers verify the proposal against the source. Regeneration requires confirmation before replacing an existing candidate.
- Explicit validation checks the edited candidate against the model and HINT, generates RDF, and runs SHACL.

**Planned.** Researchers choose when to submit a draft for scientific review. Submissions can include unresolved semantic issues.

**Deferred · Phase 1B.** Natural-language edits to selected parts of an existing candidate, if researchers need them.

## Pillar 2 — Scientific Knowledge Management

**Planned**

- Ilaria reviews the original description, proposed representation, and findings. She can correct the representation, approve it for publication, or reject the submission. Scientific approval is separate from technical validation.
- Preserve the original submission, revisions, and scientific decisions. Keep resolved issues in the permanent record.
- Classify issues by type and group related issues across scenarios for shared resolution. Resolutions may inform changes to HINT or the HI ontology.

## Pillar 3 — Query & Exploration

**Implemented · Initial exploration.** The Explorer lists all twelve original CQs. CQ1, CQ2, CQ5, CQ6, CQ7, CQ8, CQ9, CQ10, and CQ11 run against explicitly selected scenario named graphs with inference disabled. CQ3, CQ4, and CQ12 await scientific clarification or ontology development and cannot execute. Results retain source scenarios and use the existing ontology and HINT reference graphs for labels.

Cross-scenario concept search covers capabilities, team and context constraints, execution methods, and evaluation and experiment metrics. Comparison pairs selected provisional or shared sources, including at least one provisional scenario, and matches exact HINT concept identifiers within each category. GraphDB checks overlap before limiting the displayed relationship rows. Common concepts retain their distinct relationships and source evidence. The result expresses recorded vocabulary overlap and differences in the available representations. Missing assertions and scientific equivalence require researcher interpretation.

The Builder stays open in the browser while the researcher explores. FastAPI validates the current canonical draft before staging its RDF under a unique named graph inside an uncommitted GraphDB transaction. GraphDB can query that graph alongside explicitly allowed shared graphs. The transaction is rolled back after the request, so a valid or explored draft does not enter the shared corpus. This keeps the slice independent of persistent workspaces and researcher accounts.

Researchers can also upload multiple canonical or complete Pillar 1 draft JSON files. The Explorer keeps these scenarios in browser memory and lets the researcher select the sources for each query. FastAPI revalidates every selected scenario through the canonical RDF/HINT/SHACL pipeline. Upload identifiers distinguish files with equal canonical scenario IDs, and each request uses fresh staging graph IRIs. Their canonical entity identities remain intact, so repeated copies of one use case do not establish the distinct use cases required by CQ10.

The operator supplies the IDs of saved graphs with an explicit scientific approval decision. If no such graph is available, the Explorer stages the bundled S1–S7 reference scenarios in the query transaction and labels them as experimental. Future review and publication metadata belongs to Pillar 2.

**Later.** More competency questions, SPARQL exploration, and LLM explanations grounded in query results.

## Persistence — preferred direction

- Use one GraphDB repository for scenario named graphs and linked lifecycle metadata. Express metadata in a separate workflow vocabulary.
- FastAPI registers each scenario once for review and exploration. Track its identity, owner, lifecycle status, and history. Retain original descriptions and draft JSON even before scenario RDF can be generated.
- Test draft storage, review updates, and scoped queries in GraphDB before deciding whether SQLite is needed.

## Open engineering decisions

- **Workspace lifecycle and access.** Decide draft retention, researcher identification, and workspace permissions.
- **Revision history.** Decide which intermediate revisions to retain and how to keep the review handoff simple.
- **Issue clustering.** Decide how to represent and group issues and whether LLM assistance is useful.
