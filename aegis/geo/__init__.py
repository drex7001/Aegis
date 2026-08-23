"""Geospatial values: what a geometry claim may say, and how to read it (T56, spec 10 §4).

Nothing here knows a domain name. A geometry claim is found by asking the
ontology which predicate carries a property of type ``geo``
(``Ontology.predicates_carrying``), so a second domain gets all of this by
declaring a type that implements the platform ``place`` interface (Article XIV).

The value is **one** object with four fields, because they are one assertion:

    {"geometry": {…RFC 7946…}, "accuracy_m": 5000,
     "admin_level": "locality", "derivation": "admin_unit_centroid"}

Modelled separately (H-21), asserted together — an accuracy radius without its
geometry means nothing, and four independent claims could disagree in ways that
have no interpretation.
"""

from aegis.geo.values import (
    GeoValue,
    GeoValueError,
    geometry_kind,
    parse_geo_value,
    validate_geo_value,
)

__all__ = [
    "GeoValue",
    "GeoValueError",
    "geometry_kind",
    "parse_geo_value",
    "validate_geo_value",
]
