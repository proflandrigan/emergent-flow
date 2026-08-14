"""Banner-output tests for ``serve()``.

These verify the startup banner WITHOUT binding a real Uvicorn server and
WITHOUT writing cache/flows/runs dirs. All side-effecting setup calls are
monkeypatched away before ``serve()`` is invoked.

The monkeypatch targets mirror the real structure of ``app.serve()``:

* ``configure_cache``/``configure_artifacts``/``configure_flows``/
  ``configure_runs``/``configure_session_auth`` are module attributes of
  :mod:`emergentflow.server.app` (imported at module top).
* ``register_builtin_personas`` is imported INSIDE ``serve()`` from
  ``emergentflow.collab.persona_defs``, so it is NOT an ``app`` attribute --
  we patch the ``persona_defs`` module instead.
* ``uvicorn`` is imported INSIDE ``serve()`` (``import uvicorn``), so it is
  NOT an ``app`` attribute -- we patch the real ``uvicorn`` module.
"""

import importlib

import uvicorn

import emergentflow.collab.mcp as mcp_mod
import emergentflow.collab.persona_defs as persona_defs

# ``emergentflow.server```__init__ re-exports ``app = create_app()``, which shadows the
# actual ``emergentflow.server.app`` submodule for ``from ... import app``. Load the real
# module explicitly so ``serve()`` and the module-level config functions are reachable.
app_module = importlib.import_module("emergentflow.server.app")


class TestServeBanner:
    def _neutralize_setup(self, monkeypatch) -> None:
        monkeypatch.setattr(app_module, "configure_cache", lambda *a, **k: None)
        monkeypatch.setattr(app_module, "configure_artifacts", lambda *a, **k: None)
        monkeypatch.setattr(app_module, "configure_flows", lambda *a, **k: None)
        monkeypatch.setattr(app_module, "configure_runs", lambda *a, **k: None)
        monkeypatch.setattr(app_module, "configure_session_auth", lambda *a, **k: None)
        monkeypatch.setattr(persona_defs, "register_builtin_personas", lambda: None)
        monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)

    def test_non_loopback_prints_token_hint(self, monkeypatch, capsys) -> None:
        self._neutralize_setup(monkeypatch)

        app_module.serve(host="0.0.0.0", port=8765, open_browser=False, session_token="secret-tok")

        out = capsys.readouterr().out
        assert "Session bearer token: secret-tok" in out
        assert "serving the local canvas at http://127.0.0.1:8765" in out

    def test_loopback_has_no_token_hint(self, monkeypatch, capsys) -> None:
        self._neutralize_setup(monkeypatch)

        app_module.serve(host="127.0.0.1", port=8765, open_browser=False)

        out = capsys.readouterr().out
        assert "serving the local canvas at http://127.0.0.1:8765" in out
        assert "Session bearer token" not in out

    def test_serve_sets_shared_base_to_actual_bind(self, monkeypatch) -> None:
        """serve() overwrites the shared open_in_ui base so agent-created sessions
        link to the actual (possibly non-default) bind host/port, not 8765."""
        self._neutralize_setup(monkeypatch)
        monkeypatch.setattr(mcp_mod, "OPEN_IN_UI_BASE", "http://127.0.0.1:8765")

        app_module.serve(host="127.0.0.1", port=9000, open_browser=False)

        assert mcp_mod.OPEN_IN_UI_BASE == "http://127.0.0.1:9000"

    def test_serve_non_loopback_sets_shared_base_to_browse_host(self, monkeypatch) -> None:
        """A wildcard bind (0.0.0.0) still yields a browsable 127.0.0.1 open_in_ui base."""
        self._neutralize_setup(monkeypatch)
        monkeypatch.setattr(mcp_mod, "OPEN_IN_UI_BASE", "http://127.0.0.1:8765")

        app_module.serve(host="0.0.0.0", port=9000, open_browser=False, session_token="t")

        assert mcp_mod.OPEN_IN_UI_BASE == "http://127.0.0.1:9000"
