# Epic — UI/UX Redesign: "Liquid Glass" Canvas

> Task breakdown of the design spec [`docs/design/ui-redesign-liquid-glass.md`](../docs/design/ui-redesign-liquid-glass.md).
> Modernizes the visual canvas app: replaces 100% inline styles with a CSS-variable design
> system, a dark-first adaptive theme, floating frosted-glass chrome over a full-bleed canvas,
> per-family color coding, `lucide-react` icons, and a grouped palette. **Front end only** — no
> changes to the Python SDK, the IR, codegen, or the `emergentflow serve` server contract.

**Phase:** UI polish (follows repo Epic 7 — Live Iteration).
**Lives in:** `ui/` (React 18 / Vite / Zustand / `@xyflow/react` / `highlight.js` — own toolchain, bundled into the wheel).
**Coupling (per [ADR 0013](../docs/adr/0013-single-repo-bundled-ui-topology.md) Decision 3):** the canvas **never** imports `emergentflow`; the CI boundary check stays green. This epic consumes `family` from `src/generated/catalog.json` **as-is** — no catalog/server change.
**Dependencies:** repo Epic 5 (canvas), repo Epic 6 (catalog + palette), repo Epic 7 (Inspector Results tab, SSE execution). All shipped.
**New runtime dep:** `lucide-react` (tree-shakeable SVG icons). No CSS framework.
**Blocks:** nothing downstream; this is a self-contained visual overhaul in one release.

---

## Definition of Done (epic-level)

- [ ] No component hardcodes a color, radius, blur, or spacing literal — everything references a CSS custom property in `src/styles/tokens.css`. Inline styles are replaced by tokens + primitives / utility classes.
- [ ] Dark-first theme ships; light theme works via `[data-theme="light"]` token overrides and a persisted toggle that respects `prefers-color-scheme` on first run.
- [ ] Chrome (palette, inspector, command bar, menus, toasts) renders as frosted glass; **content** (node cards, code, forms) stays solid and high-contrast (the core legibility rule).
- [ ] `backdrop-filter` degrades gracefully via `@supports`, using `--glass-fill-strong` where blur is unsupported — text never lands on a semi-transparent unblurred panel.
- [ ] `prefers-reduced-motion` is honored everywhere (no animation/transition when set).
- [ ] Each of the 6 families (`data`/`clean`/`stats`/`ml`/`nn`/`reports`) has its hue applied consistently via a single `family.ts` mapping; color is always paired with icon + label (colorblind-safe); unknown families fall back to neutral.
- [ ] The palette is a grouped 3-super-section / family-sub-group tree with search, collapse (persisted), color dots, icons, and counts — replacing the flat alphabetical list.
- [ ] **Every `data-testid` and interaction listed in §9 of the spec is preserved** — the existing test suite passes with no test edits for behavior; undo/redo, click-to-add positioning, LOD `detailed` visibility, SSE updates, and cache-badge logic are unchanged.
- [ ] `family` is threaded through `toReactFlow.ts` into `EfNodeData` (the one canvas data-plumbing change).
- [ ] The app stays runnable + green (`npm test`, `npm run typecheck`, `npm run lint` in `ui/`) at the end of **every** phase/story below.
- [ ] `backdrop-filter` cost is validated on the 500-node stress graph (`dev/generateLargeGraph.ts`); `PERF.md` is updated with the finding (and a pan-time blur-disable if needed).

---

## Story 0 — Foundations (design system, no visual change yet)

> Spec §3, §4, §6.5, Phase 0. Land the token/glass/theme/primitive substrate before any
> component migrates. The app looks unchanged after this story.

- [x] Add `lucide-react` to `ui/package.json`; `npm install` and commit the lockfile.
- [x] Create `src/styles/tokens.css` — all `:root` (dark) tokens: neutral/surface ramp (§3.1), glass tokens (§3.2), radius/spacing/elevation/typography/motion (§3.3), family hues + soft fills (§4), the `--accent` product accent (default indigo `#6366F1`), and the `[data-theme="light"]` overrides (§3.4). Include the `prefers-reduced-motion` global rule.
- [x] Create `src/styles/glass.css` — the canonical `.glass` utility (fill + `backdrop-filter` blur/saturate + hairline top highlight + drop shadow), wrapped in `@supports (backdrop-filter: blur(1px))`, with an `@supports not (...)` fallback using `--glass-fill-strong`. Add a `.glass-strong` variant for menus/popovers.
- [x] Create `src/styles/global.css` — reset + base `body`/`#root` on the canvas radial gradient (`--bg-canvas-1 → --bg-canvas-0`), base typography (`--font-ui`), and any shared utility classes.
- [x] Import the three stylesheets once in `src/main.tsx`.
- [x] Create `src/theme/family.ts` — the single `FAMILY` map (label + color + soft + `lucide` `Icon` per family) and the `familyMeta(f)` helper with the neutral fallback (§4). Nothing else may hardcode the family→token/label/icon mapping.
- [x] Create `src/theme/useTheme.ts` — dark default; toggle sets `data-theme` on `<html>`; persist to `localStorage`; use `prefers-color-scheme` for the initial value only when there is no stored choice.
- [x] Create `src/ui/` token-driven primitives so no component styles a raw `<button>`/`<input>` again: `Button` (`primary`/`secondary`/`ghost`/`icon` variants, 32px, focus-visible accent ring), `IconButton`, `Input`/`Select`, `Segmented` (segmented control), `Tooltip`, `Toast`, `Menu`/`Popover` (glass-strong). Radii/heights/motion all from tokens.
- [x] Unit-test the primitives + `familyMeta` fallback + `useTheme` persistence/initial-value logic.

---

## Story 1 — App shell: full-bleed canvas + floating glass command bar

> Spec §5, §6.4, Phase 1. Restructure the layout and collapse the header button-soup into the
> floating command bar; migrate the three toolbars onto the new primitives.

- [x] Restructure `App.tsx`: root `position: relative; height: 100vh`; the Canvas fills the root (absolute inset 0, z-0); panels become `position: absolute`, z-10, `.glass`, with a `--space-4` gutter from viewport edges.
- [x] Replace `<header>` with a floating glass command bar (top gutter): left = product mark "Emergent Flow" + server-status dot; center/right = grouped action clusters separated by thin dividers. Reserve left/right insets equal to panel width + gutter (or center it in the canvas region) so it never overlaps palette/inspector.
- [x] Migrate `IRToolbar.tsx` (File/IR: import/export), `ExecutionToolbar.tsx` (Run: Execute ▶ / Download `.py` / Clear cache), Undo/Redo (History icon buttons), and `DevControls.tsx` (de-emphasized / behind a `⋯` menu) onto `src/ui` primitives, grouped into clusters.
- [x] Make **Execute** the single primary (accent-fill) action; everything else ghost/secondary.
- [x] Replace the `server: ok` text with a colored status dot + tooltip (green/amber/red = ok/connecting/unreachable). **Keep the `server-status` testid** on the element.
- [x] Restyle exec progress as a slim determinate bar (`current/total`) and errors as a glass toast with the semantic error color. **Keep all `exec-*` regions/testids** (`exec-download`/`exec-run`/`exec-clear-cache`/`exec-progress`/`exec-error`).
- [x] Add the theme toggle (placement per open question §10 — command-bar overflow menu acceptable for v1).

---

## Story 2 — Palette: grouped sections + family sub-groups

> Spec §6.1, Phase 2. The highest user-visible payoff. Replace the flat alphabetical list.

- [x] Add the static `SECTIONS` config (Data & Prep = `[data, clean]`; Analysis = `[stats, reports]`; Modeling = `[ml, nn]`) and group `catalog.nodes` by `family`; render sections in order, with any unlisted family falling into a trailing "More" section (future-proofing).
- [x] Render 3 super-section headers (uppercase, tertiary text, light dividers; default expanded) containing **family sub-groups** — each `familyMeta(family)` → color dot + icon + display label + node count. Family sub-groups are the collapsible unit; persist expand/collapse to `localStorage`.
- [x] Node rows: show `label`; on hover, `--fam-*-soft` background + 2px left accent in `--fam-*`. Keep click-to-add unchanged (`addNodeFromSpec`, same positioning). Keep `title`/`aria-label` carrying the node `type` (the inline `family · type` subtitle is dropped — grouping conveys family).
- [x] Restyle the search box as a glass pill with a leading `Search` icon. Search filters across all groups, auto-expands groups with matches, and hides empty groups/sections; match on `label` + `type` as today. (Substring highlight is a nice-to-have, not v1.)
- [x] **Preserve `palette-search` and `palette-list` testids** (search input; scroll container).

---

## Story 3 — Node cards & edges/canvas

> Spec §6.2, §7, Phase 3. Solid cards with family accent + status ring; edge/minimap theming.

- [x] Thread `family` through `toReactFlow.ts` into `EfNodeData` (currently passes `label`/`ports`/`status`/`results` — **add `family`**). This is the only canvas data-plumbing change.
- [x] `EfNode.tsx`: solid `--surface-1` card, `--radius-md`, `--shadow-2`, `1px --border-subtle`, `width: 176`. Header = family-tinted bar with the family icon + label — use treatment **(b)** (soft fill + 3px `--fam-*` accent stripe + primary text) consistently.
- [x] Move execution status off the 1px border onto an **outer ring/glow** so family color owns the border: `ok` = no ring, `cached` = blue ring + keep 💾 badge, `error` = red ring + subtle red glow, `skipped` = 60% dimmed, `running` = animated accent-ring pulse (reduced-motion aware). Keep the existing `borderColorFor` semantic colors.
- [x] Restyle ports: `@xyflow` `Handle`s unchanged in behavior/ids; dot → 8px, filled with the family hue, `--border-strong` ring. **Keep the LOD `detailed` label-visibility logic exactly as-is.**
- [x] Retoken the results toggle / panel / cached badge (💾 may become a lucide glyph — low priority). **Preserve `ef-node`, `node-results-toggle`, `node-results`, `node-cached-badge` testids and their behavior.**
- [x] `EfEdge.tsx`: `--border-strong` default; on hover/selection tint toward the **source node's family** hue; 1.5–2px smooth bezier. (Animated flow on edges feeding a running node = nice-to-have, reduced-motion aware.)
- [x] `Canvas.tsx`: `<Background variant="dots">` uses `--grid-dot` over the radial gradient; reskin `<Controls>`/`<MiniMap>` (if present) to glass, minimap node color = family hue; selection box in `--accent` low alpha.
- [x] `NodeContextMenu.tsx`: reskin to a glass-strong popover with token menu items (keep its testids).

---

## Story 4 — Inspector: glass panel, segmented tabs, form primitives

> Spec §6.3, Phase 4.

- [ ] `Inspector.tsx`: glass panel floating right (`width: 320px`); header shows the selected node's family icon + label in the family hue.
- [ ] Restyle the Config/Code/Results tabs as a segmented control (pill track `--surface-2`, active `--surface-3` + `--text-primary`, inactive `--text-secondary`). **Preserve `inspector-tab-config|code|results` testids** and the active/`fontWeight` semantics.
- [ ] `ConfigForm.tsx`: replace raw browser inputs/selects with the `src/ui` token form controls (§6.5) — this is where most of the "dated" feel lives.
- [ ] `CodePanel.tsx`: monospace on `--surface-1`/`--font-mono`; keep `highlight.js` but swap in a dark theme that harmonizes with the palette.
- [ ] `PayloadView.tsx` / Results + empty states: swap `#666`/`#b00` literals for `--text-secondary` / a semantic error token. **Preserve `inspector`, `inspector-empty`, `results-empty-no-selection|no-run`, `results-error`, `results-list`, `results-last-run` testids.**

---

## Story 5 — Polish, fallbacks & QA

> Spec §5 (collapse rails), §8 Phase 5, §9 constraints.

- [ ] Motion pass: apply `--motion-fast`/`--motion-med`/`--motion-ease` to hover/panel-open/selection transitions — calm, never bouncy/slow.
- [ ] Reduced-motion audit: confirm every animation/transition is disabled under `prefers-reduced-motion`.
- [ ] `backdrop-filter` fallback audit: every glass surface reads correctly in the `@supports not` branch (no unblurred transparent text backgrounds).
- [ ] Light-theme QA pass across all panels/nodes/edges.
- [ ] Contrast audit (§4): all 6 family bases ≥ ~4.5:1 as text on dark surfaces; header-bar-as-background labels use `--text-on-accent`/white per contrast.
- [ ] Panel collapse: chevron to collapse palette/inspector to a thin icon-only rail (spec §5 — first-pass optional; at minimum leave the hook; confirm v1 scope per §10).
- [ ] Performance: validate `backdrop-filter` on the 500-node stress graph (`dev/generateLargeGraph.ts`); if panning frame-rate suffers, disable panel blur while the canvas pans. Record the result in `ui/PERF.md`.
- [ ] Final screenshot review (dark + light) against the spec mockups (§5, §6.1, §6.2).

---

## Open questions to resolve during the epic (spec §10)

- [ ] **Product accent** — confirm indigo `#6366F1` for primary actions, or fold "Run" into amber (`--fam-ml`) to avoid a 7th hue.
- [ ] **Panel collapse rails** — confirm whether the collapse-to-rail affordance ships in v1 or just leaves the hook.
- [ ] **Theme toggle placement** — command-bar overflow menu vs. always-visible.
- [ ] **Onboarding empty state** ("drop your first node" glass hint) — cheap/high-impact but out of the above scope; decide if it's added.

Nice-to-haves explicitly **not** in v1: palette search substring highlight, drag-from-palette (click-to-add only).

---

## Notes / Risks (carry into planning)

- **Glass on chrome, solid on content** is the non-negotiable legibility rule — never make node cards, code, or forms translucent.
- **Tokens, not literals** is what makes light/dark adaptivity free; a single hardcoded color anywhere breaks the maintainability premise and the theme.
- **The §9 constraint list is a hard contract** — restyle elements, keep every testid and every behavior. Treat any test change for behavior as a red flag.
- **No server/IR/catalog change** — consume `family` as-is; the `ui-server-boundary.md` contract and the CI `emergentflow`-import boundary check stay intact.
- **Keep `@xyflow/react`** — theme it, don't replace it.
- **Sequence keeps the app runnable** — Story 0 is invisible foundation; Stories 1–4 migrate surfaces one at a time; each phase stays green before the next.

---

### Appendix — file-by-file change map (spec Appendix A)

| File | Change |
| --- | --- |
| `ui/package.json` | + `lucide-react` |
| `src/main.tsx` | import token/glass/global CSS |
| `src/styles/{tokens,glass,global}.css` | **new** — design system |
| `src/theme/family.ts`, `src/theme/useTheme.ts` | **new** — family map + theme toggle |
| `src/ui/*` | **new** — Button/IconButton/Input/Segmented/Tooltip/Toast/Menu primitives |
| `src/App.tsx` | full-bleed layout, floating glass panels, command bar |
| `src/palette/Palette.tsx` | grouped sections + family sub-groups + color/icons |
| `src/inspector/Inspector.tsx`, `ConfigForm.tsx`, `CodePanel.tsx`, `PayloadView.tsx` | glass + tokens + segmented tabs + form primitives |
| `src/canvas/nodes/EfNode.tsx` | family header/accent, status ring, port dots |
| `src/canvas/toReactFlow.ts` | thread `family` into node data |
| `src/canvas/edges/EfEdge.tsx`, `src/canvas/Canvas.tsx`, `NodeContextMenu.tsx` | edge/minimap/background/menu theming |
| `src/exec/ExecutionToolbar.tsx`, `src/io/IRToolbar.tsx`, `src/dev/DevControls.tsx` | primitives + clustered command bar |
| `ui/PERF.md` | note re: `backdrop-filter` on large graphs |

---

*How to use this file: tick each `- [ ]` to `- [x]` as work completes. A story is done when all
its tasks are checked; the epic is done when the Definition of Done checklist is complete.*
