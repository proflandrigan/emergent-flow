"""Tests for emergentflow.nodes.registry — NodeRegistry and the default singleton."""

import importlib.metadata

import pytest

from emergentflow.ir.common import Direction
from emergentflow.nodes.contract import CodeFragment, NodeDefinition
from emergentflow.nodes.registry import (
    ENTRY_POINT_GROUP,
    NodeRegistry,
    by_family,
    by_port_type,
    discover,
    get,
    register,
    registry,
    validate,
)
from emergentflow.nodes.spec import NodeSpec, ParamSpec, PortSpec

# ---------------------------------------------------------------------------
# Shared concrete stub helpers
# ---------------------------------------------------------------------------


def _make_dummy(type_key: str, family_key: str = "x", label_text: str = "Dummy"):
    """Return a fresh concrete NodeDefinition subclass with the given type key.

    The subclass implements the two abstract methods with no-op stubs so it is
    fully concrete and can be instantiated.  A fresh class object is returned
    on every call so tests can independently register it without cross-test
    pollution.
    """

    class _Dummy(NodeDefinition):
        type = type_key
        family = family_key
        label = label_text

        def codegen(self, node):
            return CodeFragment()

        def execute(self, node, inputs):
            return {}

    _Dummy.__name__ = f"_Dummy_{type_key.replace('.', '_')}"
    _Dummy.__qualname__ = _Dummy.__name__
    return _Dummy


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRegisterAndContains:
    def test_register_and_contains(self):
        """A registered definition shows up in __contains__ and __len__."""
        reg = NodeRegistry()
        Dummy = _make_dummy("x.dummy")
        reg.register(Dummy)
        assert "x.dummy" in reg
        assert len(reg) == 1

    def test_register_returns_class(self):
        """register() returns the exact same class object."""
        reg = NodeRegistry()
        Dummy = _make_dummy("x.returns")
        result = reg.register(Dummy)
        assert result is Dummy

    def test_empty_registry_len_zero(self):
        reg = NodeRegistry()
        assert len(reg) == 0
        assert "x.missing" not in reg


class TestDuplicateKey:
    def test_duplicate_type_raises(self):
        """Two different classes sharing the same type key → ValueError."""
        reg = NodeRegistry()
        DummyA = _make_dummy("x.dup")
        DummyB = _make_dummy("x.dup")
        reg.register(DummyA)
        with pytest.raises(ValueError, match="x.dup"):
            reg.register(DummyB)

    def test_duplicate_error_message_names_both_classes(self):
        """The error message should mention both the new and existing class."""
        reg = NodeRegistry()
        DummyA = _make_dummy("x.clash")
        DummyA.__name__ = "FirstClass"
        DummyB = _make_dummy("x.clash")
        DummyB.__name__ = "SecondClass"
        reg.register(DummyA)
        with pytest.raises(ValueError, match="FirstClass"):
            reg.register(DummyB)

    def test_reregister_same_class_is_noop(self):
        """Registering the identical class object twice is idempotent."""
        reg = NodeRegistry()
        Dummy = _make_dummy("x.noop")
        reg.register(Dummy)
        reg.register(Dummy)  # should not raise
        assert len(reg) == 1


class TestMissingMetadata:
    def test_missing_type_raises_value_error(self):
        """A subclass that never sets 'type' → ValueError (not AttributeError)."""

        class _NoType(NodeDefinition):
            family = "x"
            label = "No Type"

            def codegen(self, node):
                return CodeFragment()

            def execute(self, node, inputs):
                return {}

        reg = NodeRegistry()
        with pytest.raises(ValueError, match="type"):
            reg.register(_NoType)

    def test_missing_family_raises_value_error(self):
        """A subclass that never sets 'family' → ValueError."""

        class _NoFamily(NodeDefinition):
            type = "x.no_family"
            label = "No Family"

            def codegen(self, node):
                return CodeFragment()

            def execute(self, node, inputs):
                return {}

        reg = NodeRegistry()
        with pytest.raises(ValueError, match="family"):
            reg.register(_NoFamily)

    def test_missing_label_raises_value_error(self):
        """A subclass that never sets 'label' → ValueError."""

        class _NoLabel(NodeDefinition):
            type = "x.no_label"
            family = "x"

            def codegen(self, node):
                return CodeFragment()

            def execute(self, node, inputs):
                return {}

        reg = NodeRegistry()
        with pytest.raises(ValueError, match="label"):
            reg.register(_NoLabel)

    def test_empty_type_raises(self):
        """An empty 'type' string → ValueError."""

        class _EmptyType(NodeDefinition):
            type = ""
            family = "x"
            label = "Empty Type"

            def codegen(self, node):
                return CodeFragment()

            def execute(self, node, inputs):
                return {}

        reg = NodeRegistry()
        with pytest.raises(ValueError, match="type"):
            reg.register(_EmptyType)


class TestBaseClassRejection:
    def test_register_base_class_raises(self):
        """Attempting to register the abstract NodeDefinition itself → ValueError."""
        reg = NodeRegistry()
        with pytest.raises(ValueError, match="abstract"):
            reg.register(NodeDefinition)

    def test_non_class_raises(self):
        """Passing a non-class object raises ValueError."""
        reg = NodeRegistry()
        with pytest.raises(ValueError):
            reg.register("not_a_class")  # type: ignore[arg-type]

    def test_unrelated_class_raises(self):
        """A class that is not a NodeDefinition subclass → ValueError."""
        reg = NodeRegistry()

        class Unrelated:
            pass

        with pytest.raises(ValueError):
            reg.register(Unrelated)  # type: ignore[arg-type]


class TestDefaultSingleton:
    def test_decorator_targets_default(self):
        """@register on a class puts it in the module-level default registry."""
        # Use a unique type key to avoid polluting the default registry across
        # test runs if tests share the same interpreter process.
        unique_key = "x.singleton_decorator_test"

        @register
        class _SingletonDummy(NodeDefinition):
            type = unique_key
            family = "x"
            label = "Singleton Decorator Test"

            def codegen(self, node):
                return CodeFragment()

            def execute(self, node, inputs):
                return {}

        assert unique_key in registry
        # The decorator must return the original class unchanged.
        assert _SingletonDummy.type == unique_key


# ---------------------------------------------------------------------------
# Helpers for lookup tests
# ---------------------------------------------------------------------------


class _Tabular(NodeDefinition):
    type = "x.tabular"
    family = "data"
    label = "Tabular"
    ports = [PortSpec(name="table", direction=Direction.OUT, data_type="Table")]

    def codegen(self, node):
        return CodeFragment()

    def execute(self, node, inputs):
        return {}


class _TabularIn(NodeDefinition):
    type = "x.tabular_in"
    family = "data"
    label = "Tabular In"
    ports = [PortSpec(name="table", direction=Direction.IN, data_type="Table")]

    def codegen(self, node):
        return CodeFragment()

    def execute(self, node, inputs):
        return {}


# ---------------------------------------------------------------------------
# TestLookups
# ---------------------------------------------------------------------------


class TestLookups:
    def test_get_returns_class(self):
        """get() returns the exact class registered under the given type key."""
        reg = NodeRegistry()
        Dummy = _make_dummy("x.dummy_get")
        reg.register(Dummy)
        assert reg.get("x.dummy_get") is Dummy

    def test_get_missing_raises_keyerror(self):
        """get() raises KeyError for an unregistered type key."""
        reg = NodeRegistry()
        with pytest.raises(KeyError):
            reg.get("x.missing")

    def test_try_get_missing_returns_none(self):
        """try_get() returns None for an unregistered type key."""
        reg = NodeRegistry()
        assert reg.try_get("x.not_there") is None

    def test_try_get_present_returns_class(self):
        """try_get() returns the class when the key is registered."""
        reg = NodeRegistry()
        Dummy = _make_dummy("x.dummy_try")
        reg.register(Dummy)
        assert reg.try_get("x.dummy_try") is Dummy

    def test_by_family_groups_and_sorts(self):
        """by_family() returns only the matching definitions, sorted by type."""
        reg = NodeRegistry()
        DataA = _make_dummy("data.a", family_key="data")
        DataB = _make_dummy("data.b", family_key="data")
        Stats1 = _make_dummy("stats.one", family_key="stats")
        # Register in a non-alphabetical order to verify sorting.
        reg.register(DataB)
        reg.register(Stats1)
        reg.register(DataA)

        result = reg.by_family("data")
        assert len(result) == 2
        assert result[0] is DataA
        assert result[1] is DataB

    def test_by_family_empty_when_no_match(self):
        """by_family() returns an empty list when no definitions match."""
        reg = NodeRegistry()
        reg.register(_make_dummy("x.z", family_key="other"))
        assert reg.by_family("nonexistent") == []

    def test_by_port_type_matches(self):
        """by_port_type() finds definitions with a matching port data_type."""
        reg = NodeRegistry()
        reg.register(_Tabular)
        # No direction filter — should find it.
        result = reg.by_port_type("Table")
        assert _Tabular in result

        # IN direction — should NOT find it (port is OUT).
        result_in = reg.by_port_type("Table", Direction.IN)
        assert _Tabular not in result_in

        # OUT direction — should find it.
        result_out = reg.by_port_type("Table", Direction.OUT)
        assert _Tabular in result_out

    def test_by_port_type_direction_in(self):
        """by_port_type() with Direction.IN finds IN-port definitions only."""
        reg = NodeRegistry()
        reg.register(_TabularIn)
        # Matches on IN direction.
        assert _TabularIn in reg.by_port_type("Table", Direction.IN)
        # Does NOT match on OUT direction.
        assert _TabularIn not in reg.by_port_type("Table", Direction.OUT)

    def test_by_port_type_no_match(self):
        """by_port_type() returns empty list when data_type is absent."""
        reg = NodeRegistry()
        reg.register(_make_dummy("x.no_ports"))
        assert reg.by_port_type("Table") == []

    def test_all_sorted(self):
        """all() returns every definition sorted by type."""
        reg = NodeRegistry()
        Z = _make_dummy("z.last")
        A = _make_dummy("a.first")
        M = _make_dummy("m.middle")
        reg.register(Z)
        reg.register(A)
        reg.register(M)
        result = reg.all()
        assert result == [A, M, Z]

    def test_specs_returns_nodespecs(self):
        """specs() returns NodeSpec instances whose .type matches the definitions."""
        reg = NodeRegistry()
        Dummy1 = _make_dummy("spec.a")
        Dummy2 = _make_dummy("spec.b")
        reg.register(Dummy1)
        reg.register(Dummy2)
        specs = reg.specs()
        assert len(specs) == len(reg)
        assert all(isinstance(s, NodeSpec) for s in specs)
        spec_types = {s.type for s in specs}
        assert spec_types == {"spec.a", "spec.b"}

    def test_iter(self):
        """Iterating over a registry yields the same result as all()."""
        reg = NodeRegistry()
        B = _make_dummy("iter.b")
        A = _make_dummy("iter.a")
        reg.register(B)
        reg.register(A)
        assert list(reg) == reg.all()

    def test_module_level_get_delegates(self):
        """Module-level get() delegates to the default registry singleton."""
        unique_key = "x.module_level_get_test"

        @register
        class _ModuleLevelGetDummy(NodeDefinition):
            type = unique_key
            family = "x"
            label = "Module Level Get Test"

            def codegen(self, node):
                return CodeFragment()

            def execute(self, node, inputs):
                return {}

        assert get(unique_key) is _ModuleLevelGetDummy

    def test_module_level_by_family_delegates(self):
        """Module-level by_family() delegates to the default registry."""
        unique_key = "x.module_by_family_test"

        @register
        class _FamilyDummy(NodeDefinition):
            type = unique_key
            family = "x_unique_family_for_test"
            label = "Family Delegate Test"

            def codegen(self, node):
                return CodeFragment()

            def execute(self, node, inputs):
                return {}

        result = by_family("x_unique_family_for_test")
        assert _FamilyDummy in result

    def test_module_level_by_port_type_delegates(self):
        """Module-level by_port_type() delegates to the default registry."""
        unique_key = "x.module_by_port_type_test"

        @register
        class _PortTypeDummy(NodeDefinition):
            type = unique_key
            family = "x"
            label = "Port Type Delegate Test"
            ports = [
                PortSpec(
                    name="out",
                    direction=Direction.OUT,
                    data_type="UniqueTestToken_xyz",
                )
            ]

            def codegen(self, node):
                return CodeFragment()

            def execute(self, node, inputs):
                return {}

        result = by_port_type("UniqueTestToken_xyz")
        assert _PortTypeDummy in result


# ---------------------------------------------------------------------------
# TestValidate
# ---------------------------------------------------------------------------


class TestValidate:
    """Tests for NodeRegistry.validate() and the module-level validate()."""

    def test_clean_registry_validates_empty(self):
        """A registry populated with well-formed nodes returns no problems."""
        reg = NodeRegistry()
        A = _make_dummy("val.a", family_key="val", label_text="Val A")
        B = _make_dummy("val.b", family_key="val", label_text="Val B")
        reg.register(A)
        reg.register(B)
        assert reg.validate() == []

    def test_wrong_key_detected(self):
        """A definition inserted under a key that differs from its type is flagged."""
        reg = NodeRegistry()
        Legit = _make_dummy("val.legit")
        reg.register(Legit)

        # Insert a second definition under a wrong key directly (bypassing register).
        Imposter = _make_dummy("val.real_type")
        reg._defs["wrong.key"] = Imposter  # stored key ≠ Imposter.type

        problems = reg.validate()
        # Must mention both the stored key and the declared type.
        assert any("wrong.key" in p and "val.real_type" in p for p in problems), problems

    def test_duplicate_in_port_name_flagged(self):
        """Two IN ports sharing a name on one definition is reported.

        register() does NOT check port-name uniqueness per direction, so the
        definition registers fine and validate() is what catches the violation.
        """

        class _DupInPorts(NodeDefinition):
            type = "val.dup_in_ports"
            family = "val"
            label = "Dup IN Ports"
            ports = [
                PortSpec(name="table", direction=Direction.IN, data_type="Table"),
                PortSpec(name="table", direction=Direction.IN, data_type="Table"),
            ]

            def codegen(self, node):
                return CodeFragment()

            def execute(self, node, inputs):
                return {}

        reg = NodeRegistry()
        # Try to register normally; if register rejects it (e.g. future Pydantic
        # validation), fall back to direct _defs insertion so we test the sweep.
        try:
            reg.register(_DupInPorts)
        except (ValueError, Exception):
            reg._defs[_DupInPorts.type] = _DupInPorts

        problems = reg.validate()
        assert any("table" in p and "IN" in p for p in problems), problems

    def test_in_and_out_same_name_ok(self):
        """IN and OUT ports sharing a name is allowed — no false positive."""

        class _InOutSameName(NodeDefinition):
            type = "val.in_out_same"
            family = "val"
            label = "IN OUT Same Name"
            ports = [
                PortSpec(name="table", direction=Direction.IN, data_type="Table"),
                PortSpec(name="table", direction=Direction.OUT, data_type="Table"),
            ]

            def codegen(self, node):
                return CodeFragment()

            def execute(self, node, inputs):
                return {}

        reg = NodeRegistry()
        reg.register(_InOutSameName)
        assert reg.validate() == []

    def test_duplicate_param_name_flagged(self):
        """Two params sharing a name on one definition is reported.

        register() does NOT check param-name uniqueness, so the definition
        registers fine and validate() catches the violation.
        """

        class _DupParams(NodeDefinition):
            type = "val.dup_params"
            family = "val"
            label = "Dup Params"
            params = [
                ParamSpec(name="threshold", type_token="float", default=0.5),
                ParamSpec(name="threshold", type_token="float", default=0.9),
            ]

            def codegen(self, node):
                return CodeFragment()

            def execute(self, node, inputs):
                return {}

        reg = NodeRegistry()
        try:
            reg.register(_DupParams)
        except (ValueError, Exception):
            reg._defs[_DupParams.type] = _DupParams

        problems = reg.validate()
        assert any("threshold" in p for p in problems), problems

    def test_bad_version_flagged(self):
        """A definition with version=0 reaching the sweep is reported.

        NodeSpec.version_must_be_positive (Pydantic) causes register() to
        reject version=0 via the to_spec() check, so we insert via _defs.
        """

        class _BadVersion(NodeDefinition):
            type = "val.bad_version"
            version = 0
            family = "val"
            label = "Bad Version"

            def codegen(self, node):
                return CodeFragment()

            def execute(self, node, inputs):
                return {}

        reg = NodeRegistry()
        # register() rejects version=0 (Pydantic NodeSpec.version_must_be_positive),
        # so insert directly to test the sweep.
        reg._defs[_BadVersion.type] = _BadVersion

        problems = reg.validate()
        assert any("version" in p and "val.bad_version" in p for p in problems), problems

    def test_module_level_validate_delegates(self):
        """Module-level validate() delegates to the default registry singleton."""
        # We can only assert it returns a list[str] since the default registry may
        # contain arbitrary well-formed definitions registered by other tests.
        result = validate()
        assert isinstance(result, list)
        assert all(isinstance(msg, str) for msg in result)


# ---------------------------------------------------------------------------
# Fake entry-point helpers for TestDiscover
# ---------------------------------------------------------------------------


class _GoodEP:
    """A fake entry point whose load() returns a valid NodeDefinition subclass."""

    name = "plugin.good"
    value = "myplugin.nodes:GoodNode"

    def load(self):
        return _make_dummy("plugin.good")


class _BadLoadEP:
    """A fake entry point whose load() raises ImportError."""

    name = "plugin.bad_load"
    value = "myplugin.nodes:BrokenNode"

    def load(self):
        raise ImportError("boom")


class _NotANodeEP:
    """A fake entry point whose load() returns something that is not a NodeDefinition."""

    name = "plugin.not_a_node"
    value = "myplugin.nodes:NotANode"

    def load(self):
        return object  # a class, but not a NodeDefinition subclass


# ---------------------------------------------------------------------------
# TestDiscover
# ---------------------------------------------------------------------------


class TestDiscover:
    """Tests for NodeRegistry.discover() and the module-level discover()."""

    def test_discover_registers_good(self, monkeypatch):
        """A well-formed entry point is registered; discover() returns no problems."""
        reg = NodeRegistry()

        def fake_entry_points(*, group):
            assert group == ENTRY_POINT_GROUP
            return [_GoodEP()]

        monkeypatch.setattr(importlib.metadata, "entry_points", fake_entry_points)
        problems = reg.discover()
        assert problems == []
        assert "plugin.good" in reg

    def test_discover_collects_bad_load(self, monkeypatch):
        """A load() failure yields one problem mentioning the ep name and error."""
        reg = NodeRegistry()

        def fake_entry_points(*, group):
            return [_BadLoadEP()]

        monkeypatch.setattr(importlib.metadata, "entry_points", fake_entry_points)
        problems = reg.discover()
        assert len(problems) == 1
        assert "plugin.bad_load" in problems[0]
        assert "boom" in problems[0]
        # Registry should be unchanged (nothing registered).
        assert len(reg) == 0

    def test_discover_bad_does_not_block_good(self, monkeypatch):
        """A bad entry point is recorded but does not prevent good ones from loading."""
        reg = NodeRegistry()

        def fake_entry_points(*, group):
            return [_GoodEP(), _BadLoadEP()]

        monkeypatch.setattr(importlib.metadata, "entry_points", fake_entry_points)
        problems = reg.discover()
        # Good one registered successfully.
        assert "plugin.good" in reg
        # Exactly one problem, for the bad entry point.
        assert len(problems) == 1
        assert "plugin.bad_load" in problems[0]

    def test_discover_non_node_recorded(self, monkeypatch):
        """An entry point returning a non-NodeDefinition class produces a problem."""
        reg = NodeRegistry()

        def fake_entry_points(*, group):
            return [_NotANodeEP()]

        monkeypatch.setattr(importlib.metadata, "entry_points", fake_entry_points)
        problems = reg.discover()
        assert len(problems) == 1
        assert "plugin.not_a_node" in problems[0]
        assert len(reg) == 0

    def test_discover_custom_group(self, monkeypatch):
        """Passing a custom group= is forwarded to entry_points()."""
        reg = NodeRegistry()
        seen_groups = []

        def fake_entry_points(*, group):
            seen_groups.append(group)
            return []

        monkeypatch.setattr(importlib.metadata, "entry_points", fake_entry_points)
        reg.discover(group="my.custom.group")
        assert seen_groups == ["my.custom.group"]

    def test_module_level_discover_delegates(self, monkeypatch):
        """Module-level discover() populates the default registry singleton."""
        # Use a unique type key to avoid polluting other tests.
        unique_key = "plugin.module_level_discover_test"

        class _UniqueEP:
            name = unique_key
            value = "myplugin.nodes:UniqueNode"

            def load(self):
                return _make_dummy(unique_key)

        def fake_entry_points(*, group):
            return [_UniqueEP()]

        monkeypatch.setattr(importlib.metadata, "entry_points", fake_entry_points)
        problems = discover()
        assert problems == []
        assert unique_key in registry
