"""Tests for the process-local HTML report store (Epic 7 Story 3)."""

from __future__ import annotations

import threading

from emergentflow.server import reports as reports_mod
from emergentflow.server.reports import ReportStore, _hash_html


def test_put_returns_content_hash() -> None:
    store = ReportStore()
    html = "<!DOCTYPE html><html><body>hi</body></html>"
    assert store.put(html) == _hash_html(html)


def test_round_trip_get_returns_stored_html() -> None:
    store = ReportStore()
    html = "<html><body>report</body></html>"
    h = store.put(html)
    assert store.get(h) == html


def test_put_is_idempotent_by_content() -> None:
    store = ReportStore()
    html = "<html>same</html>"
    assert store.put(html) == store.put(html)


def test_get_unknown_hash_returns_none() -> None:
    store = ReportStore()
    assert store.get("0123456789abcdef") is None


def test_get_rejects_malformed_key(tmp_path) -> None:
    # Wrong length and non-hex / traversal-shaped keys never touch the fs.
    store = ReportStore(root=tmp_path)
    assert store.get("../secret") is None
    assert store.get("nothex!!") is None
    assert store.get("") is None


def test_explicit_root_is_used(tmp_path) -> None:
    store = ReportStore(root=tmp_path / "reports")
    h = store.put("<html>x</html>")
    assert (tmp_path / "reports" / f"{h}.html").is_file()


def test_execute_path_attaches_report_hash_to_html_payload() -> None:
    from emergentflow.server.reports import get_default_store
    from emergentflow.server.service import _results_to_payloads

    html = "<!DOCTYPE html><html><body>profile report</body></html>"
    payloads = _results_to_payloads({"n-node": {"report": html}})
    payload = payloads["n-node"]["report"]
    assert payload["kind"] == "html"
    assert payload["value"] == html  # value stays inline (additive hash)
    assert "report_hash" in payload
    assert get_default_store().get(payload["report_hash"]) == html


def test_execute_path_leaves_non_html_payloads_unchanged() -> None:
    from emergentflow.server.service import _results_to_payloads

    payloads = _results_to_payloads({"n-node": {"out": 42}})
    payload = payloads["n-node"]["out"]
    assert payload["kind"] == "scalar"
    assert "report_hash" not in payload


def test_get_default_store_is_thread_safe(monkeypatch) -> None:
    # Regression test: get_default_store() used a naive check-then-act lazy-init.
    # Concurrent /execute requests run on separate worker threads (app.py's
    # run_in_executor dispatch), so two threads racing the very first call could
    # each construct their own ReportStore -- whichever lost the race to set the
    # global left its reports unreachable via get_default_store() ever after.
    monkeypatch.setattr(reports_mod, "_default_store", None)
    thread_count = 16
    barrier = threading.Barrier(thread_count)
    stores: list[ReportStore] = []
    lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        store = reports_mod.get_default_store()
        with lock:
            stores.append(store)

    threads = [threading.Thread(target=worker) for _ in range(thread_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(stores) == thread_count
    assert len({id(s) for s in stores}) == 1
