# Recommender data prep — packed lists to a fitted two-tower model

Recommenders (`ef.recommend`, see [ADR 0021](./adr/0021-recommender-systems-architecture.md))
consume a **tidy long** interaction frame — one row per user-item event — but exports from an
upstream system often arrive **packed**: one row per user, with list-valued columns bundling
each user's items, ratings, and preferences together. This guide walks through unpacking a
packed export into the shapes `ef.recommend.prepare_interactions` and `ef.recommend.fit_two_tower`
expect, using `ef.clean.explode_lists` and `ef.clean.encode_lists`.

## The packed input

A typical packed export — one row per user, three list-valued columns:

| user_id | item_ids     | ratings   | fav_genres      |
|---------|--------------|-----------|------------------|
| u1      | [i7, i2, i9] | [5, 3, 4] | [rock, jazz]     |
| u2      | [i2, i5]     | [2, 5]    | [pop]            |

`item_ids` and `ratings` are index-aligned per row (the 1st item goes with the 1st rating, and
so on); `fav_genres` is a separate, unrelated list that describes the user, not any one
interaction.

## Step 1 — explode interactions to long form

`ef.clean.explode_lists` explodes one or more list columns **together** (zipped by position,
not cross-joined), so `item_ids` and `ratings` stay paired:

```python
import emergentflow as ef

events = ef.clean.explode_lists(
    packed, columns=["item_ids", "ratings"]  # zipped, not cross-joined
)
# -> one row per (user_id, item_ids, ratings), fav_genres list repeated per row
```

Resulting long table:

| user_id | item_ids | ratings | fav_genres   |
|---------|----------|---------|--------------|
| u1      | i7       | 5       | [rock, jazz] |
| u1      | i2       | 3       | [rock, jazz] |
| u1      | i9       | 4       | [rock, jazz] |
| u2      | i2       | 2       | [pop]        |
| u2      | i5       | 5       | [pop]        |

`item_ids` and `ratings` are still index-aligned — each exploded row pairs the item with its own
rating, not some other row's. `fav_genres` isn't in `columns`, so it's simply repeated once per
exploded row; it isn't touched here because it describes the user, not the interaction — it gets
encoded separately in Step 3.

## Step 2 — prepare the interaction matrix

Feed the long frame to `ef.recommend.prepare_interactions`, telling it which column holds the
item id (`item_ids`, the exact column name `explode_lists` produced above) and which holds the
event value:

```python
interactions = ef.recommend.prepare_interactions(
    events, user_col="user_id", item_col="item_ids", value_col="ratings",
)
```

This validates the columns, aggregates any duplicate (user, item) pairs, and returns a sparse
`InteractionMatrix` — the shape every `ef.recommend` fitter, including `fit_two_tower`, consumes.

## Step 3 — build user-side features with multi-hot encoding

The two-tower model's user tower wants **numeric** feature columns keyed by `user_id` — one row
per user. Go back to the *packed* frame (already one row per user) and multi-hot encode the
`fav_genres` list into indicator columns with `ef.clean.encode_lists`:

```python
user_features = ef.clean.encode_lists(
    packed[["user_id", "fav_genres"]], column="fav_genres", prefix="genre",
)
# user_id | genre_jazz | genre_pop | genre_rock
```

Each distinct genre becomes its own `0`/`1` indicator column, named `f"{prefix}_{label}"` in
sorted label order. The user tower consumes exactly this shape: numeric columns keyed by
`user_id`, one row per user — multi-hot indicators are a natural fit.

## Step 4 — item-side features

The item tower is symmetric: a frame with an `item_id` column plus numeric feature columns, one
row per item. If items carry their own list-valued tags, the same `encode_lists` call works —
just keyed by `item_id` instead of `user_id`:

```python
item_features = ef.clean.encode_lists(
    packed_items[["item_id", "tags"]], column="tags", prefix="tag",
)
# item_id | tag_indie | tag_live | tag_remix
```

(`packed_items` here is whatever one-row-per-item source frame you have — a separate items
table, or a dedupe of an items export — it isn't derived from the exploded `events` frame.)

## Step 5 — fit the two-tower model

With `interactions`, `user_features`, and `item_features` in hand:

```python
recommender = ef.recommend.fit_two_tower(
    interactions,
    user_features=user_features,
    item_features=item_features,
    params={"epochs": 5, "user_embedding_dim": 16, "item_embedding_dim": 16},
)
recs = ef.recommend.recommend(recommender, n=10)
```

Notes:
- `fit_two_tower` needs the optional `torch` extra (see the root `CLAUDE.md` / `pyproject.toml`
  for how to install it into a dev venv — it's intentionally not a hard dependency).
- `user_embedding_dim` must equal `item_embedding_dim`.
- The id columns used to align `user_features`/`item_features` to the interaction matrix default
  to `user_id`/`item_id`; override them via the `user_id_col`/`item_id_col` params if your
  feature frames use different column names.
- Other tunable params: `user_tower_layers`, `item_tower_layers`, `loss`,
  `negative_sampling_ratio`, `epochs`, `batch_size`, `learning_rate`, `seed`.

## On the canvas

The same pipeline maps directly onto canvas nodes: **Explode Lists** and **Encode Lists**
(Transform category) turn the packed export into a long interactions frame and one or two
multi-hot feature frames; **Prepare Interactions** turns the long frame into the interaction
matrix; **Fit Two-Tower Recommender** takes three input ports — the interaction matrix plus both
feature frames (item features and user features) — and produces the fitted recommender, same as
the `fit_two_tower` call above.

## Gotchas

- **Empty lists drop under `drop_empty=True`** (the `explode_lists` default) — a row whose
  exploded column is an empty list produces no output row at all, rather than a row with `NaN`
  item/rating.
- **Aligned (multi-column) explode requires equal-length lists per row** — if `item_ids` and
  `ratings` don't have the same length for a given user, `explode_lists` raises rather than
  silently misaligning them.
- **Only numeric feature columns feed the towers** — non-numeric columns in `user_features` /
  `item_features` are ignored by the tower, so encode anything categorical (e.g. via
  `encode_lists` or one-hot encoding) before fitting.
- **Each user/item appears at most once in a feature frame** — `user_features` must have one row
  per unique `user_id` (same for `item_features`/`item_id`); duplicate ids are rejected rather
  than silently aggregated.
