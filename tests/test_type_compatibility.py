import pytest
from pydantic import ValidationError

from emergentflow.ir.common import Cardinality
from emergentflow.types.compatibility import (
    Compatibility,
    check_cardinality,
    is_compatible,
)
from emergentflow.types.registry import TypeDef, TypeRegistry


@pytest.fixture
def reg() -> TypeRegistry:
    """Isolated registry: DataFrame, HTML, and TimeSeries <: DataFrame."""
    r = TypeRegistry()
    r.register(TypeDef(token="DataFrame"))
    r.register(TypeDef(token="HTML"))
    r.register(TypeDef(token="TimeSeries", supertypes=("DataFrame",)))
    return r


class TestIsCompatible:
    def test_exact_match(self, reg):
        result = is_compatible("DataFrame", "DataFrame", registry=reg)
        assert result.verdict is Compatibility.COMPATIBLE
        assert "DataFrame" in result.reason

    def test_subtype(self, reg):
        result = is_compatible("TimeSeries", "DataFrame", registry=reg)
        assert result.verdict is Compatibility.COMPATIBLE
        assert "subtype" in result.reason

    def test_subtype_wrong_direction_is_incompatible(self, reg):
        # DataFrame is NOT a subtype of TimeSeries.
        result = is_compatible("DataFrame", "TimeSeries", registry=reg)
        assert result.verdict is Compatibility.INCOMPATIBLE

    def test_any_as_target(self, reg):
        result = is_compatible("DataFrame", "any", registry=reg)
        assert result.verdict is Compatibility.COMPATIBLE

    def test_any_as_source(self, reg):
        result = is_compatible("any", "DataFrame", registry=reg)
        assert result.verdict is Compatibility.COMPATIBLE

    def test_wildcard_beats_unknown(self, reg):
        # "any" on either side wins even when the other token is unregistered.
        assert is_compatible("any", "Nope", registry=reg).verdict is Compatibility.COMPATIBLE
        assert is_compatible("Nope", "any", registry=reg).verdict is Compatibility.COMPATIBLE

    def test_unregistered_source_is_unknown(self, reg):
        result = is_compatible("Mystery", "DataFrame", registry=reg)
        assert result.verdict is Compatibility.UNKNOWN
        assert "Mystery" in result.reason

    def test_unregistered_target_is_unknown(self, reg):
        result = is_compatible("DataFrame", "Mystery", registry=reg)
        assert result.verdict is Compatibility.UNKNOWN

    def test_identical_unregistered_tokens_are_unknown_not_compatible(self, reg):
        # Locked precedence: unknown wins over exact match for unregistered tokens.
        result = is_compatible("Mystery", "Mystery", registry=reg)
        assert result.verdict is Compatibility.UNKNOWN

    def test_known_unrelated_is_incompatible(self, reg):
        result = is_compatible("HTML", "DataFrame", registry=reg)
        assert result.verdict is Compatibility.INCOMPATIBLE
        assert "HTML" in result.reason
        assert "DataFrame" in result.reason

    def test_result_records_both_tokens(self, reg):
        result = is_compatible("HTML", "DataFrame", registry=reg)
        assert result.source_type == "HTML"
        assert result.target_type == "DataFrame"

    def test_deterministic(self, reg):
        a = is_compatible("HTML", "DataFrame", registry=reg)
        b = is_compatible("HTML", "DataFrame", registry=reg)
        assert a == b

    def test_result_is_frozen(self, reg):
        result = is_compatible("DataFrame", "DataFrame", registry=reg)
        with pytest.raises(ValidationError):
            result.verdict = Compatibility.INCOMPATIBLE


class TestCheckCardinality:
    def test_one_zero_edges_ok(self):
        assert check_cardinality(Cardinality.ONE, 0).ok is True

    def test_one_single_edge_ok(self):
        assert check_cardinality(Cardinality.ONE, 1).ok is True

    def test_one_two_edges_is_violation(self):
        result = check_cardinality(Cardinality.ONE, 2)
        assert result.ok is False
        assert "2" in result.reason

    def test_many_permits_fan_in(self):
        result = check_cardinality(Cardinality.MANY, 5)
        assert result.ok is True
        assert result.inbound_count == 5

    def test_port_name_appears_in_reason(self):
        result = check_cardinality(Cardinality.ONE, 3, port_name="features")
        assert "features" in result.reason

    def test_deterministic(self):
        a = check_cardinality(Cardinality.ONE, 2)
        b = check_cardinality(Cardinality.ONE, 2)
        assert a == b


class TestRulesAsData:
    """ADR 0012: the compatibility verdict is reproducible client-side from the
    registry's serialized catalog (``to_dict()``) alone — no Python objects."""

    def test_verdict_reproducible_from_serialized_catalog(self, reg):
        data = reg.to_dict()
        types = set(data["types"])
        top = data["top"]
        edges = data["subtypes"]  # list of [subtype, supertype] pairs

        def supertypes(token):
            seen = set()
            stack = [sup for (sub, sup) in edges if sub == token]
            while stack:
                current = stack.pop()
                if current in seen:
                    continue
                seen.add(current)
                stack.extend(sup for (sub, sup) in edges if sub == current)
            return seen

        def client_verdict(source, target):
            if source == top or target == top:
                return Compatibility.COMPATIBLE
            if source not in types or target not in types:
                return Compatibility.UNKNOWN
            if source == target:
                return Compatibility.COMPATIBLE
            if target in supertypes(source):
                return Compatibility.COMPATIBLE
            return Compatibility.INCOMPATIBLE

        pairs = [
            ("DataFrame", "DataFrame"),
            ("TimeSeries", "DataFrame"),
            ("DataFrame", "TimeSeries"),
            ("HTML", "DataFrame"),
            ("any", "DataFrame"),
            ("DataFrame", "any"),
            ("Mystery", "DataFrame"),
            ("Mystery", "Mystery"),
        ]
        for source, target in pairs:
            expected = client_verdict(source, target)
            actual = is_compatible(source, target, registry=reg).verdict
            assert actual == expected, (source, target, actual, expected)
