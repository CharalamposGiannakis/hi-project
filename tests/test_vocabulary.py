import json
from pathlib import Path

import pytest

from hi_scenario.rdf import _concept
from hi_scenario.vocabulary import CATEGORIES, export_vocabulary


FRONTEND_VOCABULARY = Path(__file__).resolve().parent.parent / "frontend" / "src" / "lib" / "hint-vocabulary.json"


def test_frontend_vocabulary_matches_thesaurus():
    # Regenerate with: python -m hi_scenario.vocabulary frontend/src/lib/hint-vocabulary.json
    assert FRONTEND_VOCABULARY.read_text(encoding="utf-8") == export_vocabulary()


@pytest.mark.parametrize("category", CATEGORIES)
def test_every_offered_concept_is_accepted_by_the_rdf_mapping(category):
    offered = json.loads(export_vocabulary())[category]
    assert offered
    for concept in offered:
        _concept(concept["id"], category)
        assert concept["label"] and concept["definition"]
