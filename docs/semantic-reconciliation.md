# Canonical Scenario Semantic Reconciliation

This document compares the seven reconstructed HI scenarios (S1–S7) against their original research RDF representations. It identifies preserved information, modeling differences, and unresolved questions requiring scientific clarification.

## Sources and Comparison Method

The original scenarios are defined in `ontology/scenarios_kgs.ttl`, with the HI ontology and HINT thesaurus providing the reference vocabulary.

Automated regression tests compare the complete original and generated RDF graphs, accounting for application-assigned entity identifiers. They verify all relationships, entity types, and literal values, including language tags.

The comparison establishes representational fidelity, not scientific correctness. Any discrepancies and provisional modeling decisions are documented below.

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

The following assertion is omitted:

```turtle
hi-s2:InteractionExplainRisk hi:towardsGoal hi-s2:GoalSafeToolRetrieval .
```

The problem is that `hi:towardsGoal` has `hi:TaskExecution` as its domain, while the original assertion uses an `Interaction`. This would imply that the Interaction is also a TaskExecution.

**Possible solution:** Extend or revise the ontology to support a direct Interaction–Goal relationship.

S2 contains 10 tasks, but only 3 are directly required by the goal: unlocking the cabinet, opening it, and retrieving the tool.

The heavy-lifting task has two recorded executions, while the tool-retrieval task has none. Executions can contribute to the goal even when their tasks are not directly required.

The scenario also contains 5 separate experiments and 5 evaluations. Each experiment has two hypotheses, stored as plain text without language tags. **181 unchanged + 14 labels = 195**; there are no additional semantic relationships. See [S2 regression tests](../tests/test_s2.py).

### S3 — Group Deliberation

The original S3 references `hint:AssessCommunicationAccuracyTask`, which is not defined in HINT. We replaced it with the existing Task concept `hint:AssessCommunicationAccuracy`, whose label is "Assess Communication Accuracy Task".

This appears to be a naming inconsistency in the original research. **Proposed decision:** Keep the replacement, subject to Ilaria's confirmation.

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

The application uses a structured JSON model to describe HI scenarios. Each scenario contains one use case, one HI team, one goal, and a collection of tasks and agents. Researchers can also add contexts, capabilities, executions, interactions, experiments, and evaluations.

The model does not attempt to expose every possible ontology relationship. It focuses on the structures needed to reconstruct the seven reference scenarios.

Some choices are worth noting:

- **Entity identity:** Each entity has its own identifier within a scenario. Two agents with the same name or HINT concept remain separate individuals. The application does not assume that agents appearing in different scenarios are identical.
- **Goals and tasks:** A goal can require specific tasks rather than every task in the scenario. Older JSON examples without this selection are interpreted as requiring all tasks.
- **Contexts and constraints:** Constraints can belong independently to the team or its context. When a context exists, the application also creates a relationship expressing its influence on the team. This is an application convention, not necessarily a relationship asserted in the original scenario.
- **Capabilities and executions:** Capabilities connect agents with tasks they can perform. Executions describe actual task performance. The application preserves this distinction and explicitly generates relevant inverse relationships.
- **Experiments and evaluations:** Experiments, evaluations, metrics, and hypotheses remain separate. Hypothesis text and language information are preserved.
- **Interactions:** Interactions identify participating agents and may be linked to executions. The application does not invent these links when they are absent.

The generator also adds display labels and, in some scenarios, HINT agent classifications. These additions are documented in the comparison tables above.

The current representation is a practical starting point. It should not be interpreted as a complete implementation of the HI ontology.

## Validation and knowledge storage

The application validates scenarios in several steps. Python checks the JSON structure and references, verifies HINT concepts, generates RDF, and runs SHACL validation.

These checks establish technical consistency, but they do not guarantee that a scenario is scientifically correct or that every ontology requirement has been examined.

We identified some limitations in the existing resources:

- The SHACL shapes do not fully cover contexts or task capability requirements.
- The execution shape targets `hi:Execution`, while the ontology and application use `hi:TaskExecution`.
- The ontology assigns `hi:operatesInContext` to agents, while the application also uses it for teams.

These issues remain unchanged and require further consideration.

GraphDB stores the ontology, HINT vocabulary, and individual scenarios in separate named graphs. The current configuration does not enable OWL inference, so the application explicitly generates some relationships that could otherwise be inferred.

Automated tests compare generated scenarios against the original research RDF and identify known differences. Successful validation or import does not mean that Ilaria has approved the scientific interpretation.

## Competency-query coverage

The research material defines twelve Competency Questions (CQs). They describe what researchers should be able to investigate using the knowledge graph.

**Currently, only CQ1 is implemented and verified in the application.** It retrieves the composition of a stored HI team, including its members and their roles.

The remaining questions have different requirements:

| Questions | Current situation |
|---|---|
| CQ2–3 | Concern capabilities, tasks, and possible team compositions. Relevant information exists, but application queries remain unverified. |
| CQ4 | Depends on inferred relationships that the current GraphDB configuration does not provide. |
| CQ5–8 | Concern interactions, methods, evaluations, experiments, and metrics. Relevant relationships exist, but the queries are not implemented in the application. |
| CQ9–11 | Concern constraints and contextual phenomena. Some queries require adaptation to the application's scenario identifiers and relationships. |
| CQ12 | Concerns compliance with contextual constraints, which the current model does not explicitly represent. |

An independent offline comparison also found different results for CQ3, CQ7, CQ9, and CQ10 between the original research data and the reconstructed scenarios. These differences relate to representation choices already documented above.

This comparison does not establish which results are scientifically correct.

Further investigation of the competency questions belongs to [Issue #15](https://github.com/CharalamposGiannakis/hi-project/issues/15).