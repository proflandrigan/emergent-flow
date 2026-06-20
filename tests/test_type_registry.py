import pytest
from pydantic import ValidationError

from colonymind.types.registry import (
    TOP_TYPE,
    TypeDef,
    TypeRegistry,
    register_type,
    registry,
)


class TestTypeRegistry:
    def test_fresh_registry_has_only_top_type(self):
        """Fresh registry has only the top type."""
        reg = TypeRegistry()
        assert TOP_TYPE == "any"
        assert TOP_TYPE in reg
        assert len(reg) == 1
        assert reg.is_registered(TOP_TYPE)

    def test_type_def_rejects_empty_whitespace_token(self):
        """TypeDef rejects empty/whitespace token."""
        with pytest.raises(ValidationError):
            TypeDef(token="")
        with pytest.raises(ValidationError):
            TypeDef(token="   ")

    def test_register_get_try_get_contains(self):
        """register + get/try_get/contains works correctly."""
        reg = TypeRegistry()
        typedef = TypeDef(token="DataFrame")
        reg.register(typedef)

        assert reg.get("DataFrame") == typedef
        assert reg.try_get("DataFrame") == typedef
        assert "DataFrame" in reg

        with pytest.raises(KeyError):
            reg.get("Unknown")

        assert reg.try_get("Unknown") is None

    def test_idempotent_re_registration(self):
        """Idempotent re-registration does not raise and leaves len unchanged."""
        reg = TypeRegistry()
        typedef = TypeDef(token="X")
        reg.register(typedef)
        initial_len = len(reg)

        reg.register(typedef)  # Should be idempotent

        assert len(reg) == initial_len

    def test_conflicting_duplicate_raises(self):
        """Conflicting duplicate raises ValueError."""
        reg = TypeRegistry()
        reg.register(TypeDef(token="X"))
        with pytest.raises(ValueError):
            reg.register(TypeDef(token="X", description="different"))

    def test_self_loop_rejected(self):
        """Self-loop rejected on register."""
        reg = TypeRegistry()
        with pytest.raises(ValueError):
            reg.register(TypeDef(token="A", supertypes=("A",)))

    def test_cycle_rejected(self):
        """Cycle rejected on register."""
        reg = TypeRegistry()
        reg.register(TypeDef(token="A", supertypes=("B",)))
        with pytest.raises(ValueError):
            reg.register(TypeDef(token="B", supertypes=("A",)))

    def test_any_semantics(self):
        """Test semantics of the top type "any"."""
        reg = TypeRegistry()
        reg.register(TypeDef(token="DataFrame"))
        assert reg.is_subtype("DataFrame", TOP_TYPE) is True
        assert reg.is_subtype(TOP_TYPE, TOP_TYPE) is False
        assert reg.supertypes_of("DataFrame") == {"any"}
        assert reg.supertypes_of(TOP_TYPE) == set()

    def test_subtype_transitivity(self):
        """Test subtype transitivity."""
        reg = TypeRegistry()
        reg.register(TypeDef(token="A"))
        reg.register(TypeDef(token="B", supertypes=("A",)))
        reg.register(TypeDef(token="C", supertypes=("B",)))

        assert reg.is_subtype("C", "A") is True
        assert reg.supertypes_of("C") == {"B", "A", "any"}
        assert reg.supertypes_of("C", transitive=False) == {"B", "any"}
        assert "B" in reg.subtypes_of("A")
        assert "C" in reg.subtypes_of("A")

    def test_to_dict_shape(self):
        """Test to_dict shape."""
        reg = TypeRegistry()
        expected = {"types": ["any"], "top": "any", "subtypes": []}
        assert reg.to_dict() == expected

        reg.register(TypeDef(token="DataFrame"))
        reg.register(TypeDef(token="TimeSeries", supertypes=("DataFrame",)))

        expected = {
            "types": ["DataFrame", "TimeSeries", "any"],
            "top": "any",
            "subtypes": [["TimeSeries", "DataFrame"]],
        }
        assert reg.to_dict() == expected

    def test_iteration_order(self):
        """Test iteration order is sorted by token."""
        reg = TypeRegistry()
        reg.register(TypeDef(token="Z"))
        reg.register(TypeDef(token="A"))
        reg.register(TypeDef(token="M"))

        tokens = [td.token for td in reg]
        assert tokens == ["A", "M", "Z", "any"]

    def test_default_singleton_via_register_type(self):
        """Test default singleton works via register_type."""
        token = "UniqueStubToken"
        register_type(TypeDef(token=token))
        assert token in registry
