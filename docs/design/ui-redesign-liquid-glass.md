# UI/UX Redesign Spec — "Liquid Glass" Canvas

**Status:** Draft / approved direction · **Scope:** `ui/` (React + Vite + `@xyflow/react`)
**Author:** design interview, 2026-06-30 · **Applies to:** the Emergent Flow visual canvas app

This is the implementation-facing spec for modernizing the canvas UI. It captures the
decisions made in the design interview and translates them into concrete tokens, component
specs, and a migration plan you can build against. It does **not** touch the Python SDK, the
IR, codegen, or the `emergentflow serve` server contract — only the front end in `ui/`.

---

## 1. Goals & decisions

The current UI (see §2) is functional but dated: 100% inline styles, default browser form
controls, `#ddd` hairlines, a flat alphabetical node list, and no design system or dark mode.

Approved direction from the interview:

| Decision | Choice |
| --- | --- |
| **Theme** | Dark-first, **adaptive** (light mode supported via tokens) |
| **Ambition** | **Full overhaul in one pass** — replace inline styles everywhere with a token system |
| **Panel model** | **Floating glass panels** over a full-bleed canvas |
| **Color strategy** | **Per-function color coding** — each node family gets its own hue; base stays simple/clean |
| **Sidebar structure** | Super-sections (originally 3: Data & Prep / Analysis / Modeling; superseded by issue #104 / PR #110, which grew this to 9 ML-workflow sections — see `ui/src/palette/Palette.tsx`'s `SECTIONS`) with per-family sub-groups |
| **Family palette** | **Warm-spectrum spread** (blue/teal/violet/amber/rose/green) |
| **Node cards** | **Solid card + family color accent** (glass reserved for chrome, for legibility) |
| **Icons** | **Add `lucide-react`** for family + action icons |

### Design principles

1. **Glass on chrome, solid on content.** Floating panels (palette, inspector, command bar)
   are translucent frosted glass. The things you *read and edit* — node cards, code, forms —
   stay solid and high-contrast. This is the core legibility rule.
2. **Color means function, not decoration.** Hue is reserved for the 6 families. Everything
   else is neutral. A user should learn "amber = machine learning" within a minute.
3. **Tokens, not literals.** No component hardcodes a color, radius, blur, or spacing value.
   Everything references a CSS variable. This is what makes the redesign maintainable and the
   light/dark adaptivity free.
4. **Calm motion.** "Liquid" is expressed through short, soft transitions (hover, panel
   open, selection) — never bouncy or slow. Honor `prefers-reduced-motion`.
5. **Don't break behavior or tests.** All existing `data-testid`s and interactions are
   preserved (see §9).

---

## 2. Current state (baseline)

Three-pane flex layout in `src/App.tsx`:

```
┌ header: title · server status · IRToolbar · ExecutionToolbar · DevControls · Undo/Redo ┐
├──────────┬─────────────────────────────────────────────┬──────────────────────────────┤
│ Palette  │                  Canvas                      │          Inspector           │
│ (220px)  │            (@xyflow/react)                   │           (300px)            │
│ search + │                                              │  tabs: Config/Code/Results   │
│ flat list│                                              │                              │
└──────────┴─────────────────────────────────────────────┴──────────────────────────────┘
```

- **`src/App.tsx`** — shell + header, inline styles, native `<button>`s.
- **`src/palette/Palette.tsx`** — search box + flat, alphabetically-sorted list of all 23
  nodes; each row shows `label` and a `family · type` subtitle.
- **`src/inspector/Inspector.tsx`** — right dock, 3 tabs (Config / Code / Results).
- **`src/canvas/nodes/EfNode.tsx`** — white node card, 1px status-colored border, ports as
  `@xyflow/react` `Handle`s, emoji cached badge (💾).
- **`src/exec/ExecutionToolbar.tsx`**, **`src/io/IRToolbar.tsx`**, **`src/dev/DevControls.tsx`**
  — header button clusters.
- **No global CSS.** `src/main.tsx` mounts `<App/>`; `index.html` has only `#root`.

### Catalog = the backbone of the color system

Every node in `src/generated/catalog.json` already carries a `family`. There are **6
families / 23 nodes**:

| Family | Nodes | Count |
| --- | --- | --- |
| `data` | load_csv, load_json, load_parquet, load_sample | 4 |
| `clean` | select_columns, filter_rows, drop_missing, impute_missing, cast_types | 5 |
| `stats` | describe, correlation, ttest, anova | 4 |
| `ml` | train_test_split, train_classifier, train_regressor, train_random_forest, predict, evaluate | 6 |
| `nn` | module, linear, relu | 3 |
| `reports` | generate_html_summary | 1 |

The redesign consumes `family` directly — no catalog/server change required.

---

## 3. Design tokens

All tokens are CSS custom properties defined on `:root` (dark, default) and overridden under
`[data-theme="light"]`. Introduce **`src/styles/tokens.css`** and import it once in
`src/main.tsx`. TypeScript never needs the raw values; components read `var(--…)`.

### 3.1 Neutral / surface ramp

Dark is the reference. The canvas is the darkest layer; glass panels sit above it.

```css
:root {
  color-scheme: dark;

  /* Backdrop — the canvas gradient sits behind everything */
  --bg-canvas-0: #0b0f17;   /* deep base */
  --bg-canvas-1: #111725;   /* subtle radial highlight center */
  --grid-dot:    rgba(255,255,255,0.05);

  /* Text */
  --text-primary:   rgba(255,255,255,0.92);
  --text-secondary: rgba(255,255,255,0.62);
  --text-tertiary:  rgba(255,255,255,0.40);
  --text-on-accent: #0b0f17;

  /* Solid content surfaces (node cards, code, menus) */
  --surface-1: #161c28;
  --surface-2: #1d2534;
  --surface-3: #263047;
  --border-subtle: rgba(255,255,255,0.08);
  --border-strong: rgba(255,255,255,0.16);
}
```

### 3.2 Glass tokens (the liquid-glass layer)

Glass = translucent fill + `backdrop-filter` blur + saturation boost + a hairline top
highlight (the "specular" edge) + a soft drop shadow. These four together are what read as
Apple-style liquid glass; using only blur looks flat.

```css
:root {
  --glass-fill:        rgba(22,28,40,0.55);   /* panel body */
  --glass-fill-strong: rgba(22,28,40,0.72);   /* menus / popovers need more opacity */
  --glass-blur:        20px;
  --glass-saturate:    140%;
  --glass-border:      rgba(255,255,255,0.14);
  --glass-highlight:   rgba(255,255,255,0.22); /* 1px inset top edge */
  --glass-shadow:      0 8px 32px rgba(0,0,0,0.45);
  --glass-radius:      16px;
}
```

Canonical glass recipe (a `.glass` utility class):

```css
.glass {
  background: var(--glass-fill);
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  border: 1px solid var(--glass-border);
  border-radius: var(--glass-radius);
  box-shadow:
    var(--glass-shadow),
    inset 0 1px 0 0 var(--glass-highlight);  /* the specular top edge */
}
```

**Fallback (required).** `backdrop-filter` is well supported but must degrade: wrap glass
rules in `@supports (backdrop-filter: blur(1px))`, and in the `@supports not (...)` branch
use `--glass-fill-strong` (opaque enough to read without blur). Never let text land on a
semi-transparent panel with no blur.

### 3.3 Radius, spacing, elevation, typography, motion

```css
:root {
  --radius-sm: 8px;   --radius-md: 12px;  --radius-lg: 16px;  --radius-pill: 999px;

  --space-1: 4px;  --space-2: 8px;  --space-3: 12px;
  --space-4: 16px; --space-5: 24px; --space-6: 32px;

  --shadow-1: 0 1px 2px rgba(0,0,0,0.4);
  --shadow-2: 0 4px 12px rgba(0,0,0,0.4);
  --shadow-3: 0 8px 32px rgba(0,0,0,0.45);

  --font-ui: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --font-mono: ui-monospace, "SF Mono", "JetBrains Mono", Menlo, monospace;
  --text-xs: 11px; --text-sm: 12px; --text-md: 13px; --text-lg: 15px; --text-xl: 18px;

  --motion-fast: 120ms;
  --motion-med:  200ms;
  --motion-ease: cubic-bezier(0.2, 0.8, 0.2, 1);
}
@media (prefers-reduced-motion: reduce) {
  * { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
```

### 3.4 Light theme overrides

```css
[data-theme="light"] {
  color-scheme: light;
  --bg-canvas-0: #eef1f6;  --bg-canvas-1: #f7f9fc;  --grid-dot: rgba(0,0,0,0.06);
  --text-primary: rgba(17,24,39,0.92); --text-secondary: rgba(17,24,39,0.60);
  --text-tertiary: rgba(17,24,39,0.40); --text-on-accent: #ffffff;
  --surface-1: #ffffff; --surface-2: #f3f5f9; --surface-3: #e7ebf2;
  --border-subtle: rgba(0,0,0,0.08); --border-strong: rgba(0,0,0,0.14);
  --glass-fill: rgba(255,255,255,0.55); --glass-fill-strong: rgba(255,255,255,0.78);
  --glass-border: rgba(255,255,255,0.6); --glass-highlight: rgba(255,255,255,0.9);
  --glass-shadow: 0 8px 32px rgba(31,41,55,0.16);
}
```

Theme is applied by setting `data-theme` on `<html>`; default (no attribute) = dark.

---

## 4. Family color system

Each family gets a hue with three roles: a **base** (dot, header, edge), a **soft**
translucent fill (backgrounds/hover), and an **on-surface text** color that stays legible on
dark. Warm-spectrum spread:

| Family | Display name | Icon (lucide) | `--fam-*` base | Soft fill | Notes |
| --- | --- | --- | --- | --- | --- |
| `data` | Data | `database` | `#3B82F6` blue | `rgba(59,130,246,0.14)` | loading/sources |
| `clean` | Clean | `filter` / `wand-2` | `#14B8A6` teal | `rgba(20,184,166,0.14)` | prep/transform |
| `stats` | Statistics | `sigma` / `bar-chart-3` | `#8B5CF6` violet | `rgba(139,92,246,0.14)` | analysis |
| `ml` | Machine Learning | `brain` / `cpu` | `#F59E0B` amber | `rgba(245,158,11,0.14)` | models |
| `nn` | Neural Nets | `network` / `layers` | `#EC4899` rose | `rgba(236,72,153,0.14)` | declarative nn |
| `reports` | Reports | `file-text` | `#10B981` green | `rgba(16,185,129,0.14)` | outputs |

```css
:root {
  --fam-data:    #3B82F6;  --fam-data-soft:    rgba(59,130,246,0.14);
  --fam-clean:   #14B8A6;  --fam-clean-soft:   rgba(20,184,166,0.14);
  --fam-stats:   #8B5CF6;  --fam-stats-soft:   rgba(139,92,246,0.14);
  --fam-ml:      #F59E0B;  --fam-ml-soft:      rgba(245,158,11,0.14);
  --fam-nn:      #EC4899;  --fam-nn-soft:      rgba(236,72,153,0.14);
  --fam-reports: #10B981;  --fam-reports-soft: rgba(16,185,129,0.14);
}
```

**Plumbing.** A single `family.ts` helper is the one place that maps a family string →
tokens/label/icon, so nothing else hardcodes the mapping:

```ts
// src/theme/family.ts
import { Database, Filter, Sigma, Brain, Network, FileText, type LucideIcon } from "lucide-react";

export interface FamilyMeta { label: string; color: string; soft: string; Icon: LucideIcon; }

export const FAMILY: Record<string, FamilyMeta> = {
  data:    { label: "Data",             color: "var(--fam-data)",    soft: "var(--fam-data-soft)",    Icon: Database },
  clean:   { label: "Clean",            color: "var(--fam-clean)",   soft: "var(--fam-clean-soft)",   Icon: Filter },
  stats:   { label: "Statistics",       color: "var(--fam-stats)",   soft: "var(--fam-stats-soft)",   Icon: Sigma },
  ml:      { label: "Machine Learning", color: "var(--fam-ml)",      soft: "var(--fam-ml-soft)",      Icon: Brain },
  nn:      { label: "Neural Nets",      color: "var(--fam-nn)",      soft: "var(--fam-nn-soft)",      Icon: Network },
  reports: { label: "Reports",          color: "var(--fam-reports)", soft: "var(--fam-reports-soft)", Icon: FileText },
};

export const familyMeta = (f: string): FamilyMeta =>
  FAMILY[f] ?? { label: f, color: "var(--text-secondary)", soft: "var(--surface-2)", Icon: FileText };
```

Adding a 7th family later = one row here. Unknown families fall back gracefully to neutral.

> **Accessibility.** All six bases clear ~4.5:1 against the dark surfaces when used for
> **text**; when a base hue is used as a header-bar *background*, put the header label in
> `--text-on-accent` (dark) or white per contrast, whichever passes. Color is always paired
> with the icon + label so it is never the sole signal (colorblind-safe).

---

## 5. Layout & app shell

Full-bleed canvas; panels float above it as glass cards with a gutter (`--space-4`) from the
viewport edges.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  ▛▀ command bar (floating glass, centered/top) ▀▜                         │
│                                                                           │
│  ▛▀▀▀▀▀▀▀▀▀▜                                           ▛▀▀▀▀▀▀▀▀▀▀▀▜     │
│  ▌ Palette  ▌            ◇── Load CSV ──◇              ▌  Inspector  ▌     │
│  ▌ (glass)  ▌                  │                       ▌  (glass)    ▌     │
│  ▌ grouped  ▌            ◇── Describe ──◇              ▌ Config/Code/ ▌     │
│  ▌ sections ▌      (canvas full-bleed, shows through)  ▌  Results    ▌     │
│  ▙▄▄▄▄▄▄▄▄▄▟                                           ▙▄▄▄▄▄▄▄▄▄▄▄▟     │
└─────────────────────────────────────────────────────────────────────────┘
```

- **Root** (`App.tsx`): `position: relative; height: 100vh`. The **Canvas fills the whole
  root** (absolute inset 0, z-0). Panels are `position: absolute`, z-10, with the `.glass`
  class.
- **Command bar** replaces the current `<header>`: a floating glass pill/bar, top gutter.
  Left: product mark "Emergent Flow" + a small server-status dot. Center or right: grouped
  action clusters (see §6.4). It must not overlap the palette/inspector — reserve left/right
  insets equal to panel width + gutter, or center it in the canvas region.
- **Palette**: floating left, top-aligned, `width: 264px`, max-height `calc(100vh - 2*gutter
  - commandbar)`, internal scroll.
- **Inspector**: floating right, `width: 320px`, same vertical rule.
- **Collapse**: each panel gets a chevron to collapse to a thin rail (icon-only) so power
  users can reclaim canvas. (New affordance; optional in first pass but leave the hook.)
- **Canvas background**: radial gradient `--bg-canvas-1 → --bg-canvas-0` + `@xyflow`
  `<Background variant="dots">` using `--grid-dot`. This texture is what the glass refracts,
  so it matters.

---

## 6. Component specs

### 6.1 Palette (grouped, collapsible) — `src/palette/Palette.tsx`

The headline UX change. Replace the flat list with **collapsible super-sections**, each
containing **family sub-groups**, each listing its nodes.

> **Update (issue #104 / PR #110):** the catalog grew from 6 to 17 families, and the original
> 3-section model below left 11 families dumped into "More". `SECTIONS` now has 9 sections
> tracing an ML workflow (Data → Prepare → Explore → Analyze → Model → Explain →
> LLM & Embeddings → Report → Utility) that claim all 17 families — see the live definition
> and comments in `ui/src/palette/Palette.tsx`. The shape below (family sub-groups as the
> collapsible unit, search/collapse behavior, the "More" fallback for unknown families) is
> otherwise still accurate.

```
┌ Palette ─────────────────────────┐
│  🔍 Search nodes…                 │   ← glass input, pill
├──────────────────────────────────┤
│ ▾ DATA & PREP                     │   ← super-section header (uppercase, tertiary)
│    ▸ ◧ Data            (4)        │   ← family row: color dot + icon + label + count
│    ▾ ◧ Clean           (5)        │
│        Select columns             │   ← node row: hover = family-soft bg, left accent
│        Filter rows                │
│        Drop missing               │
│        …                          │
│ ▾ ANALYSIS                        │
│    ▸ ◧ Statistics      (4)        │
│    ▸ ◧ Reports         (1)        │
│ ▾ MODELING                        │
│    ▸ ◧ Machine Learning (6)       │
│    ▸ ◧ Neural Nets     (3)        │
└──────────────────────────────────┘
```

**Section model** (original 3-section version shown for the historical shape; static config,
families come from the catalog):

```ts
const SECTIONS = [
  { id: "data-prep", label: "Data & Prep", families: ["data", "clean"] },
  { id: "analysis",  label: "Analysis",    families: ["stats", "reports"] },
  { id: "modeling",  label: "Modeling",    families: ["ml", "nn"] },
];
```

Build the palette by grouping `catalog.nodes` by `family`, then rendering sections in the
order above (any family not listed falls into a trailing "More" section — future-proofing).

Behavior:
- **Family sub-groups** are the collapsible unit (expand/collapse, persisted to
  `localStorage`). Super-section headers are lighter dividers; default all expanded.
- Each **family row**: `familyMeta(family)` → color dot + icon + display label + node count.
- Each **node row**: label; on hover, background `--fam-*-soft` and a 2px left accent in
  `--fam-*`. Click-to-add is unchanged (`addNodeFromSpec`, same positioning logic). Keep
  `title`/`aria-label` with the node `type` for discoverability (subtitle no longer shows
  `family · type` inline — the grouping conveys family).
- **Search** (`palette-search` testid preserved): filters across all groups; auto-expands
  groups with matches and **hides empty groups/sections**. Match on `label` + `type` as
  today. Highlight the matched substring (nice-to-have).
- Optional: **drag-to-canvas** is still out of scope (click-to-add only), per current v1.
- `palette-list` testid preserved on the scroll container.

### 6.2 Node cards — `src/canvas/nodes/EfNode.tsx`

**Solid** card (legibility), family color as the accent, execution status as a secondary
signal (glow/ring, not the whole border).

```
┏━━━━━━━━━━━━━━━━━━━┓
┃ ▓ ⛃ Load CSV      ┃  ← header: family-hue bar, family icon, label. status dot far right
┠───────────────────┨
┃ ● path            ┃  ← IN port row (handle + colored dot on the left)
┃            table ● ┃  ← OUT port row (right-aligned, handle on the right)
┗━━━━━━━━━━━━━━━━━━━┛
   ▸ results   💾
```

- Card: `--surface-1` background, `--radius-md`, `--shadow-2`, `1px --border-subtle`.
  `width: 176` (up from 160 for the header).
- **Header**: full-width bar tinted with the family hue. Two acceptable treatments — pick one
  and use consistently: (a) solid `--fam-*` bar with `--text-on-accent` label, or (b)
  `--fam-*-soft` fill + a 3px top/left `--fam-*` accent stripe + primary text. **(b) is
  recommended** on dark for a calmer look; still shows the family icon.
- **Status → ring, not border.** Map current `borderColorFor` to an outer ring/glow:
  `ok` = `--fam` neutral/no ring, `cached` = blue ring + keep 💾 badge, `error` = red ring +
  subtle red glow, `skipped` = dimmed 60% opacity, `running` = animated accent ring pulse
  (respect reduced-motion). Keep the semantic colors from the existing switch; just move them
  off the 1px border onto a ring so family color owns the border.
- **Ports**: `@xyflow` `Handle`s unchanged in behavior/ids; restyle the dot to 8px, filled
  with the family hue, `--border-strong` ring. Keep the LOD `detailed` visibility logic
  (labels hidden when zoomed out) exactly as-is.
- **Results toggle / panel / cached badge**: keep behavior + all testids (`ef-node`,
  `node-results-toggle`, `node-results`, `node-cached-badge`). Restyle to tokens; the 💾
  badge can become a lucide `Database`/`Save` glyph or stay emoji (low priority).
- `toReactFlow.ts` must pass `family` into `EfNodeData` so the node can theme itself (it
  currently passes `label`, `ports`, `status`, `results` — **add `family`**). This is the one
  data-plumbing change on the canvas side.

### 6.3 Inspector — `src/inspector/Inspector.tsx`

- Glass panel, floating right. Header shows the **selected node's family icon + label** in
  the family hue so the inspector visually "belongs" to the selected node.
- **Tabs** (Config / Code / Results): restyle as a segmented control — pill track in
  `--surface-2`, active segment `--surface-3` + `--text-primary`, inactive `--text-secondary`.
  Keep the underline-accent option if simpler; **preserve testids**
  `inspector-tab-config|code|results` and the `fontWeight`/active semantics.
- **Config form** (`ConfigForm.tsx`): restyle inputs/selects to the token form controls
  (§6.5). This is where most of the "dated" feeling lives (raw browser widgets).
- **Code tab** (`CodePanel.tsx`): monospace on `--surface-1`, `--font-mono`; keep
  `highlight.js` but retheme to match (a dark theme that harmonizes with the palette).
- **Results** / empty states: swap `#666`/`#b00` literals for `--text-secondary` /
  semantic error token. Preserve `results-empty-*`, `results-error`, `results-list`,
  `results-last-run` testids.

### 6.4 Command bar & toolbars — `App.tsx`, `ExecutionToolbar.tsx`, `IRToolbar.tsx`, `DevControls.tsx`

- Collapse the header button soup into **grouped clusters** inside the floating glass bar,
  separated by thin dividers:
  - **File/IR** (IRToolbar: import/export IR)
  - **Run** (ExecutionToolbar: Execute ▶, Download .py, Clear cache)
  - **History** (Undo/Redo — icon buttons)
  - **Dev** (DevControls — visually de-emphasized / behind a "⋯" menu)
- **Primary action = Execute**: solid accent button (family-neutral accent, e.g. a product
  accent — use `--fam-ml` amber or a dedicated `--accent`; pick one product accent, default
  **indigo `#6366F1` `--accent`**, distinct from family hues to avoid implying a family).
  Everything else is a **ghost/secondary** button.
- **Server status**: replace the `server: ok` text with a colored dot + tooltip
  (green/amber/red = ok/connecting/unreachable). Keep the `server-status` testid on the
  element.
- **Progress + errors** (exec): keep the `exec-progress` / `exec-error` regions and all
  `exec-*` testids; restyle progress as a slim determinate bar (`current/total`) and errors
  as a glass toast with the semantic error color.

### 6.5 Primitives (buttons, inputs, menus)

Introduce a small set of token-driven primitives (either lightweight components in
`src/ui/` or utility classes in `src/styles/global.css`) so no component styles a raw
`<button>`/`<input>` again:

- **Button** variants: `primary` (accent fill), `secondary` (`--surface-2` + border),
  `ghost` (transparent, hover `--surface-2`), `icon` (square, icon-only). Radius `--radius-sm`,
  height 32px, `--motion-fast` hover. Focus-visible ring: 2px `--accent` at 60% + offset.
- **Input / Select**: `--surface-1` bg, `1px --border-subtle`, `--radius-sm`, focus →
  `--accent` border + soft ring. Search input in the palette is a pill with a leading
  `Search` icon.
- **Segmented control**, **Tooltip**, **Toast**, **Menu/Popover** (glass-strong,
  `--glass-fill-strong`).
- **Context menu** (`NodeContextMenu.tsx`): reskin to glass-strong popover + token items.

---

## 7. Edges & canvas polish — `src/canvas/edges/EfEdge.tsx`, `Canvas.tsx`

- Edges: `--border-strong` default; **on hover/selection**, tint toward the *source node's
  family* hue for a subtle "flow" read. Slightly thicker (1.5–2px), smooth bezier.
- Optional flair (nice-to-have, reduced-motion aware): animated dash/gradient on edges
  feeding a **running** node during execution.
- `@xyflow` `<Controls>` / `<MiniMap>` (if present): reskin to glass; minimap node color =
  family hue (great overview read). `<Background>` dots use `--grid-dot`.
- Selection box / multi-select highlight: `--accent` at low alpha.

---

## 8. Implementation plan (phased, but one release)

"Full overhaul in one pass" — but sequence it so the app stays runnable and testable at each
step. Each phase is independently verifiable (`npm test`, `npm run typecheck`, `npm run lint`
in `ui/`).

**Phase 0 — Foundations (no visual change yet)**
1. Add `lucide-react` to `ui/package.json`; `npm install`.
2. Create `src/styles/tokens.css`, `src/styles/glass.css`, `src/styles/global.css`
   (reset + base `body`/`#root` on the canvas gradient, `.glass`, `@supports` fallback).
   Import in `src/main.tsx`.
3. Create `src/theme/family.ts` (§4) and `src/theme/useTheme.ts` (dark default; toggle sets
   `data-theme` on `<html>`; persist to `localStorage`; respect `prefers-color-scheme` for
   the initial value when no stored choice).
4. Create `src/ui/` primitives (Button, IconButton, Input, Segmented, Tooltip, Toast, Menu).

**Phase 1 — Shell** — Restructure `App.tsx` to full-bleed canvas + floating panels + glass
command bar; migrate the three toolbars to primitives + clusters; server-status dot.

**Phase 2 — Palette** — Grouped 3-section / family sub-group rewrite with search + collapse
+ color/icons. Highest user-visible payoff.

**Phase 3 — Nodes & edges** — `EfNode` header/accent/status-ring; thread `family` through
`toReactFlow.ts`; edge + minimap theming.

**Phase 4 — Inspector** — glass panel, segmented tabs, form-control primitives, code-panel
+ highlight.js retheme, results/empty-state tokens.

**Phase 5 — Polish** — motion pass, reduced-motion + `backdrop-filter` fallback audit,
light-theme QA, contrast audit (§4), panel collapse rails, screenshot review.

### Dependencies & tooling
- **New dep:** `lucide-react` (tree-shakeable SVGs). No other runtime deps.
- Keep the existing stack (React 18, Vite, Zustand, `@xyflow/react`, `highlight.js`). **No
  CSS framework** — plain CSS variables + a few utility classes keep the bundle lean and
  match the repo's minimalist tone. (If a styling lib is later desired, CSS Modules or
  vanilla-extract fit better than Tailwind here; not required.)
- Update `PERF.md` note if `backdrop-filter` affects large-graph frame rates — blur is
  GPU-cheap on static panels but validate on the 500-node stress graph
  (`dev/generateLargeGraph.ts`). If needed, disable panel blur while the canvas is panning.

---

## 9. Constraints — do not break

- **Preserve every `data-testid`** and its semantics — the test suite asserts on them:
  `server-status`, `palette-search`, `palette-list`, `ef-node`, `node-results-toggle`,
  `node-results`, `node-cached-badge`, `inspector`, `inspector-tab-config|code|results`,
  `inspector-empty`, `results-empty-no-selection|no-run`, `results-error`, `results-list`,
  `results-last-run`, `exec-download|run|clear-cache|progress|error`, plus any in
  `IRToolbar`/`DevControls`/`NodeContextMenu`. Restyle the elements, keep the hooks.
- **No behavior changes**: undo/redo keyboard handling, click-to-add positioning, LOD
  `detailed` visibility, SSE execution updates, cache badge logic — all unchanged.
- **No server/IR/catalog changes.** Consume `family` as-is. `ui-server-boundary.md` contract
  stays intact.
- **Keep `@xyflow/react`** as the canvas engine; theme it, don't replace it.
- Respect `prefers-reduced-motion` and provide the `backdrop-filter` fallback everywhere
  glass is used.

---

## 10. Open questions / future

- **Product accent** — spec defaults to indigo `#6366F1` for primary actions, deliberately
  outside the family palette. Confirm, or fold "Run" into amber (`ml`) if you'd rather not
  introduce a 7th hue.
- **Panel collapse rails** — first-pass optional; confirm whether it ships in v1.
- **Onboarding empty state** — the canvas has no first-run guidance today; a glass "drop your
  first node" hint is a cheap, high-impact add (not in scope above).
- **Theme toggle placement** — command bar overflow menu vs. always-visible.
- **Node search → highlight** and **drag-from-palette** are noted as nice-to-haves, not v1.

---

### Appendix A — file-by-file change map

| File | Change |
| --- | --- |
| `ui/package.json` | + `lucide-react` |
| `src/main.tsx` | import token/glass/global CSS |
| `src/styles/{tokens,glass,global}.css` | **new** — design system |
| `src/theme/family.ts`, `src/theme/useTheme.ts` | **new** — family map + theme toggle |
| `src/ui/*` | **new** — Button/Input/Segmented/Tooltip/Toast/Menu primitives |
| `src/App.tsx` | full-bleed layout, floating glass panels, command bar |
| `src/palette/Palette.tsx` | grouped sections + family sub-groups + color/icons |
| `src/inspector/Inspector.tsx`, `ConfigForm.tsx`, `CodePanel.tsx`, `PayloadView.tsx` | glass + tokens + segmented tabs + form primitives |
| `src/canvas/nodes/EfNode.tsx` | family header/accent, status ring, port dots |
| `src/canvas/toReactFlow.ts` | thread `family` into node data |
| `src/canvas/edges/EfEdge.tsx`, `src/canvas/Canvas.tsx`, `NodeContextMenu.tsx` | edge/minimap/background/menu theming |
| `src/exec/ExecutionToolbar.tsx`, `src/io/IRToolbar.tsx`, `src/dev/DevControls.tsx` | primitives + clustered command bar |
| `ui/PERF.md` | note re: `backdrop-filter` on large graphs |
