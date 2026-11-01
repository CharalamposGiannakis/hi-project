# Canonical scenario semantic reconciliation

This reference describes how the canonical S1–S7 JSON examples relate to the asserted research RDF. It records the current representation and its known differences, not research approval or a change to the source. See [README](../README.md) for application setup and canonical import operations, and the [deployment runbook](deployment.md) for operations and access controls. Pending implementation work belongs in [Issue #1](https://github.com/CharalamposGiannakis/hi-project/issues/1) and other GitHub Issues.

## Sources and comparison method

The authoritative asserted graphs are in [scenarios_kgs.ttl](../ontology/scenarios_kgs.ttl). Concepts and predicates are checked against the original [HI Ontology](../ontology/hi-ontology.ttl) and [HINT thesaurus](../ontology/hi-thesaurus.ttl); those files and the [SHACL shapes](../ontology/hi-shacl.ttl) are unchanged by reconstruction.

The full-graph regression tests extract every triple whose subject or object is in a scenario's research namespace, without filtering predicates. Explicit, unique mappings connect source individuals to application-assigned individuals and verify entity/type coverage. Comparisons preserve complete RDF terms, including literal text, datatype, and language. The tests assert the exact missing and additional sets, not just counts or a supported-predicate projection.

Throughout this document, `hi:` is `https://w3id.org/hi-ontology#`, `hint:` is `https://w3id.org/hi-thesaurus/`, and `hi-sN:` is `https://w3id.org/hi-ontology/scenarios/N/`. HINT's actual concept IRIs use `/`, despite `#` in its namespace metadata.

## Scenario coverage

“Preserved unchanged” allows only the explicit individual-IRI mapping. A provisional replacement changes an assertion and is **not** counted as unchanged. “Omissions” counts source assertions absent without replacement. Generated counts include the replacements and the additional statements classified below.

| Canonical scenario | Original assertions | Preserved unchanged | Provisional replacements | Omissions | Generated RDF |
| --- | ---: | ---: | ---: | ---: | ---: |
| [S1 — Personal Assistant HI](../examples/s1.json) | 120 | 120 | 0 | 0 | 127 |
| [S2 — Collaborative Manipulation](../examples/s2.json) | 182 | 181 | 0 | 1 | 195 |
| [S3 — Group Deliberation](../examples/s3.json) | 125 | 124 | 1 | 0 | 135 |
| [S4 — Autonomous Tutoring](../examples/s4.json) | 142 | 142 | 0 | 0 | 154 |
| [S5 — Hybrid Medical Diagnosis](../examples/s5.json) | 129 | 126 | 2 | 1 | 139 |
| [S6 — Campus Energy Negotiation](../examples/s6.json) | 139 | 139 | 0 | 0 | 150 |
| [S7 — Virtual Museum Guide](../examples/s7.json) | 160 | 157 | 3 | 0 | 173 |

The distinction between other additions matters:

- **Logically entailed additions** follow from an ontology axiom but were not explicitly asserted in the source. The generator materializes them; GraphDB inference remains disabled.
- **Application conventions** are explicitly generated modeling assumptions absent from the source and are not claimed to be logically entailed.
- **Display labels** are `rdfs:label` literals supplied by example names. They are additional application metadata, not original research assertions or replacements for source comments.

| Scenario | Additional entailed triples | Additional application conventions | Additional display labels |
| --- | ---: | ---: | ---: |
| S1 | 0 | 0 | 7 |
| S2 | 0 | 0 | 14 |
| S3 | 1 | 0 | 9 |
| S4 | 0 | 2 | 10 |
| S5 | 0 | 3 | 8 |
| S6 | 0 | 2 | 9 |
| S7 | 1 | 2 | 10 |

For each row, original = unchanged + replacements + omissions; generated = unchanged + replacements + entailed additions + conventions + labels. No other differences are accepted by the regression tests.

## Source differences and research-owner questions

The provisional alignments and unresolved omissions below remain **pending Ilaria's confirmation or clarification**. They do not establish corrected research terminology, aliases, or formal equivalence. Reconstruction does not assert `owl:sameAs` or `skos:exactMatch` for these choices, weaken HINT category validation, or edit source RDF.

### S1 — Personal Assistant HI

All 23 source individuals and 120 assertions are preserved, including the Goal and three Task descriptions as English-tagged `rdfs:comment` literals. The example includes Context, four capabilities, three executions, three experiments, three evaluations, and one interaction. All three tasks remain goal requirements. The only additions are seven plain display labels, so **120 + 7 = 127**. See the [S1 full semantic regression](../tests/test_scenario.py).

### S2 — Collaborative Manipulation

All 40 individuals are represented. The sole omitted assertion is:

```turtle
hi-s2:InteractionExplainRisk hi:towardsGoal hi-s2:GoalSafeToolRetrieval .
```

The ontology declares `hi:towardsGoal` with domain `hi:TaskExecution`, while the source subject is an Interaction. Its intended meaning remains unresolved; the model has no Interaction–Goal field and does not invent an execution link.

All ten Task individuals remain, but only `TaskUnlockCabinet`, `TaskOpenCabinet`, and `TaskRetrieveTool` are directly required by the goal. `TaskHeavyLift` has two executions; `TaskRetrieveTool` has none. Executions can target the goal while realizing tasks outside its direct requirements. Five evaluations and five experiments retain separate identities, and all ten hypotheses remain plain literals without language tags or explicit datatypes. **181 unchanged + 14 labels = 195**; there are no additional semantic relationships. See [S2 regression tests](../tests/test_s2.py).

### S3 — Group Deliberation

All 24 individuals are represented. For `hi-s3:TaskAssessCommunicationAccuracy hi:hasTaskConcept`, the source IRI `https://w3id.org/hi-thesaurus/AssessCommunicationAccuracyTask` is undefined. The example provisionally uses `https://w3id.org/hi-thesaurus/AssessCommunicationAccuracy`. That defined Task-category concept has label “Assess Communication Accuracy Task” and a corresponding definition. This is a project alignment pending Ilaria's confirmation, not an equivalence assertion.

The source asserts `CapabilityMetaAnalysis hi:allowsTask TaskAssessCommunicationAccuracy` but omits its inverse. The generator adds `TaskAssessCommunicationAccuracy hi:requiresCapability CapabilityMetaAnalysis`, logically entailed by the ontology's inverse-property axiom.

Both human jurors remain distinct and share one SelfReporting capability individual. Five executions include two realizations of `TaskProvideStatement`; one evaluation covers all five. The experiment retains three metrics and English-tagged hypotheses. Two independent interactions involve all three agents without execution links. **124 unchanged + 1 replacement + 1 entailed inverse + 9 labels = 135**. See [S3 regression tests](../tests/test_s3.py).

### S4 — Autonomous Tutoring

All 26 individuals and 142 assertions are preserved, including seven English descriptions and English-tagged hypotheses. Beyond ten display labels, two application conventions add:

```turtle
hi-s4:AITutor hi:hasAgentConcept hint:ArtificialAgent .
hi-s4:HumanLearner hi:hasAgentConcept hint:HumanAgent .
```

The generator derives these links from agent kind. They are category-consistent but absent from the source and not logically entailed by an agent's RDF type. **142 unchanged + 2 conventions + 10 labels = 154**. See [S4 regression tests](../tests/test_s4.py).

### S5 — Hybrid Medical Diagnosis

All 24 individuals are represented. The source uses Metric-category concepts as evaluation concepts; the example provisionally uses the defined generic `hint:Evaluation` for these two assertions:

| Source subject and predicate | Source object | Provisional object |
| --- | --- | --- |
| `hi-s5:EvalDiagnosisAccuracy hi:hasEvaluationConcept` | `hint:DiagnosisAccuracyMetric` | `hint:Evaluation` |
| `hi-s5:EvalExplanationClarity hi:hasEvaluationConcept` | `hint:ExplanationClarityMetric` | `hint:Evaluation` |

The original metric links remain intact, and the two evaluations and experiments retain separate identities. Generic Evaluation is selectable in the form. Whether these alignments reflect the intended evaluation terminology remains pending Ilaria's clarification.

The following assertion is omitted because `hi:hasInteractionConcept` is undeclared in the checked-in ontology; its intended status remains unresolved:

```turtle
hi-s5:InteractionClinicalDialogue hi:hasInteractionConcept hint:Interaction .
```

The dialogue still has its type, participants, intent, modality, description, and both original explanation-execution links. Descriptions and hypotheses retain English tags. Three additional application conventions are not source assertions or entailments:

```turtle
hi-s5:AIDiagnosticAssistant hi:hasAgentConcept hint:ArtificialAgent .
hi-s5:HumanClinician hi:hasAgentConcept hint:HumanAgent .
hi-s5:ContextClinicalConsultation hi:hasInfluenceOn hi-s5:HITeamDiagnosis .
```

The last statement follows the application's unconditional Context-influence convention; it is not a source assertion or a logically entailed S5 fact. **126 unchanged + 2 replacements + 3 conventions + 8 labels = 139**. See [S5 regression tests](../tests/test_s5.py).

### S6 — Campus Energy Negotiation

All 26 individuals and 139 assertions are preserved, with no omissions or replacements. HINT identifiers `AllocationNegotationTask` and `NegotationImpactEvaluation` retain their source spellings. Both hypotheses remain plain literals without language tags or explicit datatypes.

The human grid operator and AI building agent share an Explaining capability, perform separate explanation executions, and share the evaluation. The human explanation execution has no interaction episode; no link is inferred. The two added agent-concept conventions are `AIBuildingAgent → hint:ArtificialAgent` and `HumanGridOperator → hint:HumanAgent` via `hi:hasAgentConcept`. **139 unchanged + 2 conventions + 9 labels = 150**. See [S6 regression tests](../tests/test_s6.py).

### S7 — Virtual Museum Guide

All 29 explicitly typed individuals are represented. The source additionally mentions two unresolved local intent IRIs only as objects; these are not silently mapped as equivalent individuals. Three assertions use provisional replacements:

| Source subject and predicate | Source object | Provisional object |
| --- | --- | --- |
| `hi-s7:InteractionVRGuidedTour hi:hasInteractionIntentConcept` | `hi-s7:IntentGuide` | `hint:GuideIntent` |
| `hi-s7:InteractionQA hi:hasInteractionIntentConcept` | `hi-s7:IntentAnswer` | `hint:AnswerIntent` |
| `hi-s7:ExecProvideProfile hi:hasMethodConcept` | `hint:SelfReportingMethod` | `hint:DataCollectionMethod` |

`hint:SelfReportingMethod` is undefined in HINT. The selected Method-category concept describes collecting multimodal, self-reported, or sensor data; the two selected intents are defined InteractionIntent concepts. These choices remain provisional pending Ilaria's confirmation. No source assertion is omitted without replacement, and the undefined names are not accepted as aliases.

Three constraints (`PrivacyConstraint`, `TransparencyConstraint`, `AccessibilityConstraint`) are asserted independently on both Team and Context, preserving all six source statements. All seven executions share the original evaluation; hypotheses remain English-tagged. The guided-tour interaction links only to recommendation execution, and QA only to question-answering execution.

The source's `CapabilityKGQuery hi:allowsTask TaskSemanticRetrieval` lacks the inverse. The generator adds the entailed `TaskSemanticRetrieval hi:requiresCapability CapabilityKGQuery`. Two additional agent-concept conventions link `AIVirtualGuide` to `hint:ArtificialAgent` and `HumanVisitor` to `hint:HumanAgent`. **157 unchanged + 3 replacements + 1 entailed inverse + 2 conventions + 10 labels = 173**. See [S7 regression tests](../tests/test_s7.py).

## Representation decisions

The [canonical model](../hi_scenario/model.py) and [RDF generator](../hi_scenario/rdf.py) represent one use case, one implicit team, one goal, and a task inventory. Use case, goal, and tasks select HINT concepts; the use case also has an optional HINT domain. Agents have names and one or more HINT roles, and each team includes human and artificial agents. Optional components extend this deliberately bounded representation.

- **Identity and labels:** entity IRIs use `urn:hi-app:scenario:{scenario-id}:…`, scoped by scenario, entity kind, and stable ID. The implicit Team and Context use `…:team` and `…:context`. Renaming or sharing concepts, names, kinds, or roles does not merge individuals. Different scenarios' agents are not asserted identical. Names generate plain `rdfs:label`; optional nonblank descriptions on Goal, Task, Context, Experiment, Evaluation, and Interaction generate English `rdfs:comment` separately.
- **Goal requirements:** `goal.required_tasks` is a nonempty, unique list of existing Task IDs when present. Omission means all scenario tasks for legacy compatibility; explicit empty/null selections are invalid. Legacy UI imports initialize all tasks as selected and export explicit requirements. New tasks start unselected, and removal drops the requirement reference; at least one must remain. All Task individuals are generated regardless of goal selection. Executions need not realize a directly required task.
- **Context and constraints:** optional Context selects one HINT concept, phenomena, and constraints. Independent `team_constraints` defaults to empty and can exist without Context. Changing or removing Context does not change Team selections, and constraints do not propagate between subjects. Whenever Context exists, the generator asserts Team `hi:operatesInContext` Context and Context `hi:hasInfluenceOn` Team. The latter is an S1-based application assumption and is not asserted in S5's source; it is not presented as an entailed fact.
- **Capabilities and executions:** capabilities are independent reusable entities with HINT Capability concepts and ID references to agents and tasks. Both `hi:allowsTask`/`hi:requiresCapability` and `hi:performedBy`/`hi:performsExecution` directions are explicitly generated. Each execution has a HINT TaskExecution concept, realizes one task, has one performer and an optional HINT method, and targets the scenario's goal. Capability possession does not assign an agent, establish eligibility, or infer execution data.
- **Experiments and evaluations:** each evaluation references one experiment and any number of executions; multiple executions can share one evaluation through `hi:evaluatedBy` links from executions. Metrics are selected separately for each entity. Both nonblank hypotheses are either plain literals (default) or English-tagged via `hypothesis_language: "en"`. S1, S2, and S6 preserve plain hypotheses; S3, S4, S5, and S7 preserve English-tagged ones. No datatype/language normalization is used to conceal a source difference.
- **Interactions:** participants are at least two distinct existing agents selected independently of performers. Intent and modality must belong to the correct HINT categories. Execution links are optional and many-to-many; no link is invented for interactions without episodes.
- **Validation and editing:** unknown fields, duplicate entity IDs within each kind, and unknown references are rejected. Old JSON may omit optional components. Removing an agent/task removes its capability links but retains the capability entity. Executions with deleted agent/task references, evaluations with deleted experiment/execution references, and interactions with deleted agent/execution references retain entered data and expose missing references for repair or explicit removal before preview/save.

## Ontology, SHACL, and storage assumptions

The semantic pipeline checks the Python model and HINT categories, generates sorted N-Triples, and invokes [SHACL validation](../hi_scenario/validation.py) with `inference="none"`, no OWL imports, and no mutation of the generated graph. Undefined or wrong-category vocabulary selections are rejected; provisional example choices do not weaken that policy.

SHACL conformance means only that the current shapes passed, not full ontology completeness or confirmed research semantics:

- There are no Context-specific shapes; Python performs its vocabulary checks. The shapes also do not require task capabilities.
- The execution shape targets `hi:Execution`, whereas the ontology and generated RDF use `hi:TaskExecution`. Python checks execution structure, references, and vocabulary; passing SHACL alone does not establish execution validation.
- `hi:operatesInContext` has declared domain `hi:Agent`, although the source uses it on teams. Enabling inference would also classify those teams as agents.
- Hypothesis predicates declare range `xsd:string`, but several source scenarios use language-tagged literals. The application preserves those literals rather than silently converting them.
- Inference would not repair the shape-target mismatch or turn OWL minimum-cardinality restrictions into closed-world validation. These inherited issues remain unresolved and unchanged.

GraphDB repository `hi` deliberately uses the `empty` ruleset with `owl:sameAs` optimization disabled. Application queries use explicit named graphs and `infer=false`. The generator's explicit inverse statements must be distinguished from database reasoning and from the non-entailed application conventions above.

The original ontology and HINT occupy `urn:hi-app:reference:ontology` and `urn:hi-app:reference:hint`; each scenario occupies `urn:hi-app:graph:scenario:{scenario-id}`. Canonical import compares stored and generated RDF by isomorphism, including full RDF terms; its [unit tests](../tests/test_canonical.py) and [isolated live tests](../tests/test_canonical_live.py) cover read-only inspection, idempotency, conflicts, partial recovery, CQ1, and graph protection. Import success checks the checked-in canonical representation, not resolution of its research exceptions or approval of a researcher submission. See [README importer safety](../README.md#canonical-scenario-import) for write/authorization boundaries and the [runbook](deployment.md#storage-access-and-updates) for administrator access, concurrency, and persistent storage limitations.

## Competency-query coverage

**Only CQ1 is implemented and verified by the application and canonical importer.** The [GraphDB adapter](../hi_scenario/graphdb.py) adapts the research team-composition query to explicit scenario/reference graphs and retains each member IRI. Agents sharing a name, type, or role therefore remain distinct. Names come from scenario RDF, type labels from the ontology, and role labels/definitions from HINT; missing labels return `null`, not invented text. The [persistence/API tests](../tests/test_persistence_api.py) and importer tests check this behavior.

The upstream research notebook `TEST/HI-Ontology-Test/cqs.ipynb` (not bundled in this application repository) defines the following further questions. They are **not implemented or verified by the application**, even where the corpus contains relevant facts:

| Research CQ | Subject and current applicability |
| --- | --- |
| CQ2–3 | Capability/task matching and candidate team compositions. Relevant capability and goal/task facts exist; query results and eligibility interpretation have not been validated here. |
| CQ4 | Inferred eligibility, assignment, or contextual influence. The notebook points to rules; those are not provided by the application's `empty` ruleset. |
| CQ5 | Interactions during task execution. The notebook requires an execution episode, task comment, and direct goal requirement; interactions without those links/comments are excluded. |
| CQ6 | Methods associated with goals and tasks. Execution method/task/goal links are represented, but the query has not been adapted or verified here. |
| CQ7–8 | Metrics, experiments, and hypotheses. These relationships are represented; their research queries have not been adapted or verified here. |
| CQ9–10 | Constraints and associated teams/use cases. Context influence is an application convention in S5, and Team constraints remain distinct from Context constraints. CQ10's notebook query does not itself establish that constraints are shared across distinct use cases or agents. |
| CQ11 | Contextual phenomena associated with a use case. Relevant facts exist; the query has not been adapted or verified here. |
| CQ12 | Compliance with or violation of contextual constraints. The required compliance representation is absent from the current model. |

The availability of these facts and query definitions does not establish additional CQ coverage, automated eligibility, or normative compliance reasoning.
