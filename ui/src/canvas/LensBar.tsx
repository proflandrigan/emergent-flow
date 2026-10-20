// Family lens chip row (issue #167): toggling a family highlights only nodes of the chosen families and
// dims the rest, without moving anything. Purely presentational -- Canvas owns the trace store wiring.

import { familyMeta } from "../theme/family";

export interface LensBarProps {
  /** Families present on the visible canvas, in display order. */
  families: string[];
  /** Families currently in the lens. */
  active: string[];
  onToggle: (family: string) => void;
}

export function LensBar({ families, active, onToggle }: LensBarProps): JSX.Element | null {
  if (families.length === 0) return null;
  return (
    <div
      data-testid="lens-bar"
      role="group"
      aria-label="Family lens"
      style={{
        position: "absolute",
        top: 10,
        right: 10,
        zIndex: 5,
        display: "flex",
        flexWrap: "wrap",
        justifyContent: "flex-end",
        gap: "var(--space-1)",
        maxWidth: "40%",
      }}
    >
      {families.map((family) => {
        const meta = familyMeta(family);
        const isActive = active.includes(family);
        return (
          <button
            key={family}
            type="button"
            data-testid={`lens-chip-${family}`}
            aria-pressed={isActive}
            title={`Lens: ${meta.label}`}
            onClick={() => onToggle(family)}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              padding: "2px var(--space-2)",
              borderRadius: "var(--radius-sm)",
              fontSize: "var(--text-xs)",
              cursor: "pointer",
              border: `1px solid ${isActive ? meta.color : "var(--border-subtle)"}`,
              background: isActive ? meta.soft : "var(--surface-1)",
              color: isActive ? meta.color : "var(--text-secondary)",
            }}
          >
            <meta.Icon size={12} aria-hidden />
            <span>{meta.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export default LensBar;
