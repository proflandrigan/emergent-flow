# Bug Hunt Report: emergent-flow Python package (collab focus)

## Summary
- **Scope reviewed:** an independent pass weighted toward surface the twenty-six prior reports under-covered —
  `emergentflow/collab/` (`chat_runner.py`, `session.py`, `consult.py`, `checkpoints.py`, agents, personas),
  `emergentflow/cli.py`, `emergentflow/script/`, `emergentflow/data/http/` (fetch/live/replay/protocol),
  `emergentflow/viz/`, `emergentflow/types/`, `emergentflow/connections/profiles.py`, and `emergentflow/server/runs.py`.
  The ML/ensembling (PR #153), stats, and timeseries surfaces hunted most recently were deliberately not re-hunted.
- **Confirmed findings:** 1 High, 1 Medium. Both fixed with regression tests.
- **Gates:** full suite green before and after (`3719 -> 3746` passed; +2 new regression tests), ADR-0002 equivalence
  (331 passed), `ruff check`/`ruff format`, and `mypy emergentflow/collab` all clean after the changes. All findings are
  in the collab package, which is opt-in and never eagerly imported (works-without-agents invariant intact — confirmed
  no `emergentflow.ir`/`emergentflow/__init__.py` edge imports collab).
- Overall assessment: the tsar-collab module is well-structured, but the two confirmed defects are real behavioral gaps
  in its failure/audit handling: (1) a mid-turn reader/parse exception strands a chat turn in RUNNING forever,
  silently blocking every later turn on that session until a manual Stop; (2) applying a mutation by *accepting a
  proposal* produces no checkpoint, so human-accepted edits silently vanish from the revert/audit ledger that
  `apply_direct_mutation` maintains for agent edits.

## Findings

### HIGH — A mid-stream exception in the chat turn reader strands the turn RUNNING and permanently blocks the session's chat
- **Location:** `emergentflow/collab/chat_runner.py:261` (`_read_stream` call inside `_run_turn`), `set_chat_thread_id` at `chat_runner.py:216`
- **Class:** Error handling / state-consistency (stranded RUNNING state, swallowed exception)
- **Confidence:** Confirmed
- **Description:** `_run_turn` wraps the subprocess read (`_read_stream` → `adapter.parse_line`, `store.set_chat_thread_id`, `proc.wait()`) in a `try/finally` with **no `except`**. If any exception escapes the reader (e.g. a plug-in adapter's `parse_line` throws, or the unguarded `store.set_chat_thread_id` raises `UnknownSessionError` when the session is deleted mid-turn), the `finally` pops the process/stop registrations but no code resolves the turn or records the failure — the exception merely kills the daemon thread (printed to server stderr) and the turn stays `RUNNING`. Because `start_chat_turn` (`session.py:744`) rejects any session whose most recent turn is `RUNNING`, that session's chat is permanently blocked on every subsequent `start_chat_turn` (`ChatAlreadyActiveError`), and `end_chat` does not clear a RUNNING turn's status, so there is no API recovery other than a manual Stop.
- **Evidence / Reproduction:** `repro_chat_stuck.py` registers an adapter whose `parse_line` raises `RuntimeError` when it sees a sentinel line (the CLI prints the sentinel then a normal line), then runs `_run_turn`. Pre-fix output:
  ```
  turn status after start: running
  Thread-1 (_run_turn): RuntimeError: adapter.parse_line exploded   # daemon thread dies
  turn status after _run_turn: running                                # stranded
  second turn blocked: ChatAlreadyActiveError                        # chat blocked forever
  ```
  Post-fix: the turn resolves to `FAILED` (error contains `"reader failed"`) and a second turn starts normally.
- **Impact:** A real agent CI passing malformed/triggering output (or a plugin bug, or a session being deleted mid-turn) permanently bricks that session's in-app chat with a misleading "running forever" state and no automated error surfaced to the user.
- **Remediation:** `chat_runner.py` — add a wrapper/resolution helper and catch unhandled exceptions on every path:
  - new `_settle_turn_registry(turn_id)` and `_fail_turn(store, session_id, turn, *, error)` helpers (`_fail_turn` suppresses `ChatTurnAlreadyResolvedError` and `UnknownSessionError` then settles the registry);
  - guard the plug-in getters (`get_adapter`, `adapter.build_command`) and the `Popen` OSError with `_fail_turn`;
  - wrap the `_read_stream`/`proc.stderr.read()`/`proc.wait()` block with `except Exception as exc: _fail_turn(..., error=f"chat turn reader failed: {exc}")` before the `finally`;
  - wrap the `set_chat_thread_id` call in `contextlib.suppress(UnknownSessionError)` so a deleted session can't kill the reader.
  Regression test: `tests/test_collab_chat_runner.py::TestStartChatTurn::test_mid_stream_parse_exception_fails_turn_not_leaves_it_running`.

### MEDIUM — `accept_proposal` applies a mutation without recording a checkpoint, so human-accepted edits are not revertible
- **Location:** `emergentflow/collab/session.py:331-378` (`accept_proposal` vs `apply_direct_mutation` at `session.py:409`)
- **Class:** State & consistency (incomplete audit/revert ledger)
- **Confidence:** Confirmed
- **Description:** `apply_direct_mutation` persists a `Checkpoint(kind=EDIT)` for **every** applied mutation (used by the agent MCP/`/apply` path), but `accept_proposal` — the path a human uses to accept an agent's proposal (`POST /sessions/{id}/proposals/{pid}/accept`) — applies the same kind of mutation, bumps the version, and marks the proposal ACCEPTED, yet creates **no** checkpoint. A mutation accepted via a proposal is therefore unrevertible and unledgered: the checkpoint/revert feature (PR #152) silently misses the human-accept flow, and `revert_checkpoint` cannot undo an accepted edit because no `Checkpoint` was recorded.
- **Evidence / Reproduction:** `repro_checkpoint.py`: a session with one edit via `apply_direct_mutation` has 1 checkpoint; adding an equivalent node by creating a proposal and `accept_proposal(..., ...)` leaves the checkpoint count at 1 (the accepted mutation is absent). Post-fix, the accepted mutation records an EDIT checkpoint and `revert_checkpoint` on it correctly removes the added node.
- **Impact:** Human-accepted agent proposals cannot be reverted or audited, inconsistently with the direct-apply path — an escape hatch from the checkpoint/revert coverage.
- **Remediation:** in `accept_proposal`, capture `previous_graph`/`previous_version` before `apply_mutation`, and after bumping the version create an EDIT `Checkpoint` (author `"human"`, description from `proposal.mutation.description`) exactly as `apply_direct_mutation` does, then include its id in the published `proposal_accepted` event. Regression test: `tests/test_collab_checkpoints.py::TestAcceptProposalCheckpoint::test_accept_proposal_records_an_edit_checkpoint`.

## Notes & unverified leads (optional)
These were investigated and did **not** become findings:
- **`viz/__init__.py:207` `plot_acf` `max_lags = max(1, len//2 - 1)` off-by-one** — genuinely crashes (`acf` → `IndexError`, `pacf` → `ValueError`) for a 1-observation residual series, and contradicts the docstring's "clamp to at most `len//2-1`" claim (it forces `lags=1` for `len<3`). Reachability is a fitted model with ≤1 residual — too degenerate to be high-value; left as a fragility. Candidate fix: compute `max_lags = min(nlags, max(0, len//2 - 1))` and skip rendering when `lags < 1`.
- **`data/http/fetch.py:186-239` offset/page pagination** stops only when a page returns zero records; a server whose beyond-end page echoes data can yield duplicates up to `max_pages` (bounded, so no infinite loop). Depends on upstream contract; not a library defect as-is.
- **`data/http/live.py:110`** `sep = "&" if "?" in url else "?"` yields `?&` for a URL already ending in `?`/`&`; tolerated by most servers.
- **`connections/profiles.py:265`** `payload = {"name": name, **body}` lets a literal `name=` key inside a TOML profile table override the table name, silently re-keying the profile. Requires a user to author a `name` field inside the table body — a config-authoring edge.
- **`server/runs.py` `keep=0`** evicts the just-saved run; `list()` orders by timestamp while `_evict()` orders by mtime. Low-severity degenerate/unreachable configurations.
- **`viz/plot_confusion_matrix` bare `ValueError`** (lead) — **refuted**: `sklearn.metrics.confusion_matrix` with `labels=<training classes>` does not raise on unseen labels in `y_true`; verified no exception.
- **`cli._coerce_param_value` bool-into-float** (lead) — **refuted**: line 137 already guards `type_token in ("int","float") and isinstance(value, bool)`.

## Coverage & limitations
- Reviewed `emergentflow/collab/` and the under-covered slices named above. The heavily-hunted surfaces (ml ensembles/PR #153, stats, timeseries, recommend, codegen) were not re-audited this pass; prior reports cover them.
- The chat_runner finding was reproduced with a synthetic throwing adapter; a real session-deletion-mid-turn trigger was reasoned (not reproduced) but shares the identical code path.
- `emergentflow/viz/` was read in full; `types/` registry/compatibility/catalog and `script/__init__.py` were read and found clean at reasonable effort.