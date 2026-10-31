import json
from pathlib import Path

import pytest
from rdflib.namespace import SKOS

from hi_scenario.rdf import HINT, _concept, _thesaurus
from hi_scenario.vocabulary import CATEGORIES, export_vocabulary


FRONTEND_VOCABULARY = Path(__file__).resolve().parent.parent / "frontend" / "src" / "lib" / "hint-vocabulary.json"


def test_frontend_vocabulary_matches_thesaurus():
    # Regenerate with: python -m hi_scenario.vocabulary frontend/src/lib/hint-vocabulary.json
    assert FRONTEND_VOCABULARY.read_text(encoding="utf-8") == export_vocabulary()


def test_generic_evaluation_is_offered_without_exposing_other_roots_or_losing_specific_choices():
    vocabulary = json.loads(export_vocabulary())
    roots = {
        category for category, choices in vocabulary.items()
        if any(choice["id"] == category for choice in choices)
    }
    assert roots == {"Evaluation"}
    assert _concept("Evaluation", "Evaluation") == HINT.Evaluation
    specific = {
        str(term).removeprefix(str(HINT))
        for term in _thesaurus().transitive_subjects(SKOS.broader, HINT.Evaluation)
        if term != HINT.Evaluation
    }
    assert {choice["id"] for choice in vocabulary["Evaluation"]} == specific | {"Evaluation"}


@pytest.mark.parametrize("category", CATEGORIES)
def test_every_offered_concept_is_accepted_by_the_rdf_mapping(category):
    offered = json.loads(export_vocabulary())[category]
    assert offered
    for concept in offered:
        _concept(concept["id"], category)
        assert concept["label"]
        # Some capability category concepts have no definition in the source.
        definitions = {str(value) for value in _thesaurus().objects(HINT[concept["id"]], SKOS.definition)}
        if definitions:
            assert concept["definition"] in definitions
        else:
            assert concept["definition"] == ""
