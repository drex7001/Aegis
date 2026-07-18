"""Projection weight unit tests (speckit T10, spec 02 §6)."""

import pytest

from aegis.ontology import load
from aegis.projections import CONFIDENCE_TAGS, WEIGHTS
from tests.support.paths import ONTOLOGY_PATH

pytestmark = pytest.mark.requirement("Article-XIII", "T10")


@pytest.fixture(scope="module")
def ontology():
    return load(ONTOLOGY_PATH)


def test_projection_weights_match_spec() -> None:
    assert WEIGHTS == {
        "confirmed": 1.0,
        "probably_true": 0.7,
        "possibly_true": 0.55,
        "doubtful": 0.4,
        "improbable": 0.2,
        "cannot_judge": 0.4,
    }


def test_reverse_maps_cover_every_credibility_value(ontology) -> None:
    for value in ontology.grading.values_for("credibility"):
        assert value in WEIGHTS
        assert CONFIDENCE_TAGS[value] in {"EXTRACTED", "INFERRED", "AMBIGUOUS"}
