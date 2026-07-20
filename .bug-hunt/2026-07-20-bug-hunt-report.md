# Bug Hunt Report: emergent-flow (delta since 2026-07-14 hunt)

## Summary
- Scope reviewed: everything added or changed between commit `5781588` (the prior bug hunt's baseline)
  and `HEAD` (`b25ec65`) — the recommender-system family (`emergentflow/recommend/`, Epic 15 Story
  Groups B–E: baselines, content-based, collaborative filtering, deep recommenders, hybrids,
  evaluation/metrics, interaction splitting, plus all `recommend_*`/`prepare_interactions` reference
  nodes), text embeddings (`emergentflow/embed/`, `embed_text` node, and the `llm/` client-seam changes
  that support it), the UI inspector's new curated per-algorithm param widgets (`ui/src/inspector/
  ConfigForm.tsx`) and the persona slash-command chat integration (both the `ui/src/session/` client
  side and `emergentflow/collab/chat_runner.py`/`persona_defs.py` backend side), and a set of smaller
  diffs (`ml.select_features`/`ml.compare_models`, the four warehouse adapters' `truncated`-flag fix,
  four new `viz_plot_*` recommender-eval nodes, and MANY-cardinality fan-in support in
  `codegen/context.py`/`codegen/executor.py`/`server/service.py`). Four parallel reviewers each ran the
  full Discovery → Verify loop over a disjoint slice of this delta and reported back only reproduced
  findings.
- Tooling baseline across the reviewed slices: `ruff check` — clean. `mypy` — clean. Targeted
  `pytest -k` runs and the full `-m equivalence` suite (261 passed) — all passing.
- Confirmed findings: **0 Critical, 1 High, 2 Medium, 0 Low**.
- Overall assessment: the newest and largest addition, the recommender system (Epic 15), held up well
  in backend logic — the reviewers only found one real bug there (a baseline-quality issue in the
  `random` recommender, not a crash), and the codegen/execute equivalence invariant continues to hold
  by construction across every algorithm sampled, including the two-tower and hybrid-switching paths
  where prior fixes already landed. The one High-severity finding is on the UI side: the new curated
  list-typed param widget for recommender hyperparameters silently corrupts numeric list values,
  which is a real, easily-triggered crash on the happy path of configuring the deep recommenders
  (NCF, two-tower) or `hybrid_weighted` through the canvas — and it's actively normalized by its own
  regression test, which asserts the corrupted (stringified) value as expected output. The persona
  slash-command integration, `select_features`/`compare_models`, the warehouse `truncated`-flag fix,
  and the new viz nodes were all clean.

## Findings

### High — Curated list-typed kwargs in the recommender/inspector form always write string arrays, corrupting `list[int]`/`list[float]` params and crashing the fitter
- **Location:** `ui/src/inspector/ConfigForm.tsx:437-457` (`EstimatorParamsField`'s `kwarg.type === "list"` branch, added in commit `4f0dc5d`); same root cause reachable from the generic `ui/src/inspector/widgets.ts` "list" widget used by non-curated params.
- **Class:** Type coercion / API contract misuse
- **Confidence:** Confirmed
- **Description:** The curated-kwarg "list" widget splits comma-separated user input on `,` and writes
  back a `string[]` unconditionally — there's no branch for numeric list items. This hits every
  recommender whose curated kwarg is declared as a list of numbers: `recommend.fit` with
  `algorithm=ncf` (`mlp_layers`, default `[32,16,8]`), `algorithm=two_tower`
  (`user_tower_layers`/`item_tower_layers`), and `algorithm=tfidf` (`ngram_range`). The commit that
  added this branch (`4f0dc5d`, "handle list-typed curated params") names exactly these kwargs as its
  motivation but only preserves array *shape*, not element type — its own regression test
  (`ConfigForm.test.tsx:303-326`) asserts the round-tripped value is `["64", "32"]` (strings),
  codifying the bug as expected behavior. The same defect (the generic "list" widget in `widgets.ts`
  is unchanged by this PR) also reaches the non-curated `recommend.hybrid_weighted` node's
  `weights: list[float]` param via the plain `ParamRow` path.
- **Evidence / Reproduction:** Traced the widget's comma-split parse logic on `"32, 16, 8"` →
  `["32","16","8"]`, then fed that value to the real Python fitters:
  ```
  # ncf
  ef.recommend.fit(im, algorithm='ncf', params={'mlp_layers': ['32','16','8'], 'epochs': 1})
  # TypeError: empty(): argument 'size' (position 1) must be tuple of ints, but found element of type str at pos 0

  # tfidf
  TfidfVectorizer(ngram_range=('1','2')).fit_transform([...])
  # TypeError: can only concatenate str (not "int") to str

  # recommend.hybrid_weighted (weights: list[float])
  ef.recommend.hybrid_weighted([r1, r2], weights=['0.5','0.5'], n=3)
  # weighted_sum: TypeError: can't multiply sequence by non-int of type 'float'
  # cascade:      TypeError: bad operand type for unary -: 'str'
  # rank_fusion:  TypeError: unsupported operand type(s) for /: 'str' and 'int'
  ```
- **Impact:** Any user who edits `mlp_layers`/`*_tower_layers` on `recommend.fit` (NCF/two-tower),
  `ngram_range` on TF-IDF, or `weights` on `hybrid_weighted` through the canvas inspector — the
  intended way to configure these brand-new Epic 15 nodes — gets a graph that crashes on
  execute/compile with an opaque `TypeError` deep inside torch/sklearn/the blending code, not a clear
  validation message. This hits the deep-recommender and hybrid nodes on their default happy path,
  since they ship with non-empty numeric-list defaults specifically meant to be tuned.
- **Remediation:** Coerce list elements by declared item type instead of always producing strings.
  For the curated path, infer numeric-ness from the kwarg's default (or add an item-type hint):
  ```ts
  const isNumericList = kwarg.default?.every?.((v: unknown) => typeof v === "number");
  const parsed = e.target.value.split(",").map((s) => s.trim()).filter((s) => s.length > 0)
    .map((s) => (isNumericList ? Number(s) : s));
  ```
  For the top-level `widgets.ts` "list" widget, thread the `list[int]`/`list[float]` distinction
  already present in `type_token` (parsed today only to decide `isListType`; the `int`/`float` suffix
  is discarded) into `parseValue` the same way. Re-run the three repros above after the fix and
  confirm they no longer raise `TypeError`.

### Medium — `random` recommender baseline re-seeds identically per user, producing collinear (often identical) recommendations across all users
- **Location:** `emergentflow/recommend/catalog.py:184-193` (`_recommend_random`)
- **Class:** Logic error — RNG misuse
- **Confidence:** Confirmed
- **Description:** `_recommend_random` creates `rng = np.random.default_rng(seed)` *inside* the
  per-user loop, using the same `seed` for every user. Since the RNG state resets to the same seed
  before each user's draw, every user with the same candidate-item list gets the identical random
  draw in the identical order. The per-user loop variable `uid` is never mixed into the seed.
- **Evidence / Reproduction:**
  ```python
  df = pd.DataFrame({'user': ['u1','u1','u2','u2','u3'], 'item': ['a','b','c','d','e']})
  im = InteractionMatrix.from_dataframe(df, user_col='user', item_col='item')
  rec = fit(im, algorithm='random', params={'seed': 42})
  recommend(rec, n=3, exclude_known=False).recommendations
  #   user_id item_id  rank
  # 0      u1       e     1
  # 1      u1       a     2
  # 2      u1       d     3
  # 3      u2       e     1   <- identical draw to u1
  # 4      u2       a     2
  # 5      u2       d     3
  # 6      u3       e     1   <- identical draw to u1/u2
  # 7      u3       a     2
  # 8      u3       d     3
  ```
  All three users get byte-identical top-3 lists in identical rank order, despite disjoint
  interaction histories. The collision persists under the realistic default `exclude_known=True`
  whenever two users' known-item sets coincide (e.g. any two cold-start users with zero history both
  get `candidates = full item list`, hence the same draw).
- **Impact:** The `random` algorithm exists specifically as a diversity/coverage-neutral baseline (per
  its own docstring and its use as an automatic reference point in `compare`/`evaluate`'s
  coverage/diversity/novelty metrics). Because recommendations collapse to the same list per distinct
  candidate-set, `evaluate`'s `diversity` metric (mean pairwise item-set overlap across users) and
  `coverage` metric (union of items recommended across users) are systematically wrong for this
  baseline — diversity is spuriously driven toward 0 and coverage toward `n/n_items` instead of
  reflecting genuine per-user randomness. Any user comparing a real algorithm against the "random"
  baseline via `compare()` gets a misleading contrast.
- **Remediation:** Seed the RNG once per call, outside the loop:
  ```python
  rng = np.random.default_rng(seed)  # create once, outside the loop
  for uid in user_ids:
      ...
      drawn = rng.choice(candidates, size=min(n, len(candidates)), replace=False)
  ```
  Re-run the repro above after the fix: `u1`/`u2`/`u3` should get different item orderings even
  though `exclude_known=False` and all three share the same candidate pool.

### Medium — `ef.embed.text()` crashes with an opaque, unrelated error for `batch_size <= 0` instead of a typed `EmbedError`
- **Location:** `emergentflow/embed/__init__.py:174-187` (`text()`, the batching loop
  `for i in range(0, len(texts), batch_size)`)
- **Class:** Boundary / missing validation
- **Confidence:** Confirmed
- **Description:** `batch_size` is a public, user-settable keyword of `ef.embed.text()` (default `64`)
  with no validation. `batch_size=0` passes `0` as `range()`'s step argument; a negative `batch_size`
  produces an empty range while `texts` is non-empty.
- **Evidence / Reproduction:**
  ```python
  ef.embed.text(df, 'text', provider='openai', model='text-embedding-3-small', client=FakeClient(), batch_size=0)
  # ValueError: range() arg 3 must not be zero
  ef.embed.text(df, 'text', provider='openai', model='text-embedding-3-small', client=FakeClient(), batch_size=-1)
  # ValueError: Length of values (0) does not match length of index (3)
  ```
  Both reproduced directly against the real `text()` function with a 3-row DataFrame and a fake
  `LLMClient`.
- **Impact:** Any direct SDK/script caller who passes a bad `batch_size` (a miscomputed value, `0` as
  an "unset" sentinel, etc.) gets a confusing, implementation-detail error instead of a clear
  `EmbedError`. Not reachable via the canvas node (`embed_text.py` doesn't expose `batch_size` as a
  `ParamSpec`), so this only affects direct `ef.embed.text()` callers — hence Medium, not High.
- **Remediation:** Validate at the top of `text()`:
  ```python
  if batch_size <= 0:
      raise EmbedError(f"batch_size must be a positive integer, got {batch_size!r}.")
  ```
  Re-run the two repros above; both should raise `EmbedError` immediately instead of the builtin
  errors.

## Notes & unverified leads (optional)

These looked suspicious but could not be verified as reproducible bugs, or were traced and refuted:

- **`GatewayClient.embed()` (`emergentflow/llm/gateway.py:185`)** builds `vectors` from
  `response.data` in the order LiteLLM returns it, trusting that order matches `request.texts`.
  OpenAI-compatible embedding responses include an `index` field precisely to guard against
  reordering, which this code ignores — if a provider ever returned out-of-order `data`, embeddings
  would silently misalign with source rows. Not verified against a real/mocked LiteLLM response with
  shuffled `index` values; would need a crafted stub to prove or refute.
- **`emergentflow/server/service.py:417-424`'s dangling-input guard vs. `codegen/context.py`'s
  documented "zero-source MANY port binds to `[]`" case.** The MANY-cardinality docstring says a
  fan-in port with zero incoming edges is legal and binds to an empty list, but the guard would raise
  `UnboundInputError` first — except it's preempted by `enforce_validation_gate`, which rejects a
  *required* IN port with zero inbound edges before reaching that guard. All three registered MANY-port
  nodes (`recommend.compare`, `recommend.hybrid_weighted`, `recommend.hybrid_switching`) leave
  `required=True`, so the zero-source-MANY case is currently unreachable end-to-end. Not a live bug
  today, but the `[]`-binding docstring claim is untested/unreachable and would misbehave the moment a
  MANY port with `required=False` is added.
- **`chat_runner.py`'s `_PERSONA_SLASH_COMMANDS`** only wires `/data-scientist`, `/researcher`,
  `/ml-engineer` — the fourth built-in persona, `data_modeller`, has no chat slash command. Traced:
  `data_modeller` is used via a different path (`consult.py`'s Mode-B one-shot, which takes
  `persona_slug` directly) and the commit adding the three chat commands names only those three —
  looks like an intentional scoping choice, not an oversight, but wasn't confirmed against the
  originating epic ticket.
- **`sessionClient.ts`'s poll fallback** uses `else if` between the `graph_replaced` version-change
  check and the new `chat_narration_added` chat-snapshot check, so only one synthetic event fires per
  poll tick if both changed simultaneously. Refuted: `sessionStore.ts`'s `refreshFromServer` always
  does a full `getSession` GET and applies the fresh `chat` state regardless of which event type
  triggered it, so a missed `chat_narration_added` in the same tick as a `graph_replaced` still
  delivers the chat update.
- **`emergentflow/recommend/catalog.py:1206`'s `_top_k_sparse`** assumes a dense `np.ndarray` input
  (`masked = sim.copy()`); currently safe since `_similarity_matrix`'s only caller path densifies
  first, but worth a second look if a future similarity type returns a sparse array.
- **Zero-positives end-to-end through `viz_plot_precision_recall_curve` → `evaluate()`** — the
  function's own degenerate-input validation was confirmed to raise a typed `VizError`, but a full
  `InteractionMatrix`/`FittedRecommender` fixture reproducing the zero-positive-class case end-to-end
  wasn't built; flagged but not chased further.
- Refuted: `compare_models`'s empty-exception-message guard
  (`(str(exc).strip().splitlines() or ["Unknown error"])[0][:200]`) correctly handles empty,
  whitespace-only, and leading-blank-line exception messages. `ReplayClient` content-hashing for embed
  requests correctly incorporates provider+model+texts, so fixtures can't cross-contaminate between
  models or with `complete()` fixtures. Warehouse adapters' `truncated`-flag fix (from the prior bug
  hunt) was re-derived and confirmed correct at the exact boundary across all four adapters. Persona
  node-namespace references in `agents/*.md` were cross-checked against the live node catalog with
  zero mismatches. `recommend.fit`'s curated-kwarg `required` markers were cross-checked
  programmatically against `RecommenderSpec.param_metadata` across all 15 registered recommenders with
  zero mismatches.

## Coverage & limitations

- **Reviewed this pass:** `emergentflow/recommend/` (catalog.py's baselines/content-based/
  collaborative/deep algorithms, `__init__.py`'s wrapper functions, `interactions.py`,
  `metrics.py`), the `recommend_*`/`prepare_interactions` reference nodes; `emergentflow/embed/`,
  `embed_text.py`, and the `llm/` budget/gateway/pricing/protocol/replay diffs; `ui/src/inspector/
  ConfigForm.tsx`/`widgets.ts`, `ui/src/session/ChatModal.tsx`/`sessionClient.ts`/`sessionStore.ts`;
  `emergentflow/collab/chat_runner.py`/`persona_defs.py`/`session.py`/`contracts.py`/`chat.py`/
  `mcp.py` diffs; `emergentflow/ml/__init__.py`'s `select_features`/`compare_models`; the four
  warehouse adapters' `truncated`-flag diffs; `emergentflow/viz/__init__.py`'s four new plot
  functions (validation paths); `codegen/context.py`/`codegen/executor.py`/`server/service.py`'s
  MANY-cardinality fan-in support.
- **Not reviewed / spot-checked only:** `_fit_tfidf_similarity`/`_recommend_tfidf_similarity`,
  `_fit_feature_knn`/`_recommend_feature_knn`, `_fit_embedding_similarity`/
  `_recommend_embedding_similarity` in `recommend/catalog.py` (lines ~697-1165); a direct
  compile_to_code-vs-execute diff script for `two_tower`/`hybrid_switching` (equivalence inferred by
  construction and the existing equivalence suite, not independently diffed this pass);
  `recommend_evaluate.py`/`recommend_compare.py` node wrappers; `ml/catalog.py`/`ml/registry.py`'s
  new ParamSpec entries (read as diff only); `select_features`/`compare_models` reference nodes in
  `nodes/examples/` (backend function reviewed, thin node wrappers not); zero-positive-class
  end-to-end through the PR-curve viz node; `ui/src/catalog/types.ts` and the regenerated
  `catalog.json`/`session_event.*` contract artifacts (spot-checked only, typecheck/lint clean, no
  drift found).
- This hunt was scoped to the *delta* since the 2026-07-14 report; areas unchanged since then
  (stats family, most of `ui/src/canvas/*`, `ui/src/promptlab/*`, `ui/src/connections/*`, the
  individual collab CLI adapters beyond `base.py`) were out of scope here and retain whatever
  coverage the prior report gives them.
- All three confirmed findings are High/Medium: the UI list-widget bug is the most user-visible
  (crashes the canvas happy-path for newly-added, prominently-featured node types) and is rated High
  because it requires no unusual configuration — just editing a default numeric-list param through the
  UI as intended. Neither Medium finding is destructive; each needs either a specific baseline
  algorithm choice (`random`) or a non-default/direct-SDK argument (`batch_size<=0`) to trigger.
