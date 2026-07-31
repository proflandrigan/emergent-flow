import { Button } from "../ui/Button";

export interface SelectionToolbarProps {
  count: number;
  onRunSelectedOnly: () => void;
  onRunToSelected: () => void;
  onGroup?: () => void;
  onUngroup?: () => void;
  onExtractToComposite?: () => void;
}

export function SelectionToolbar({
  count,
  onRunSelectedOnly,
  onRunToSelected,
  onGroup,
  onUngroup,
  onExtractToComposite,
}: SelectionToolbarProps): JSX.Element {
  return (
    <div
      data-testid="selection-toolbar"
      style={{
        position: "absolute",
        bottom: "var(--space-4)",
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 10,
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--space-2)",
        padding: "var(--space-2) var(--space-3)",
        borderRadius: "var(--radius-md)",
        background: "var(--surface-2)",
        border: "1px solid var(--border-subtle)",
      }}
    >
      <span style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)" }}>
        {count} nodes selected
      </span>
      <Button
        variant="secondary"
        data-testid="run-selected-only"
        onClick={onRunSelectedOnly}
      >
        Run selected only
      </Button>
      <Button
        variant="secondary"
        data-testid="run-to-selected"
        onClick={onRunToSelected}
      >
        Run to selected
      </Button>
      {onGroup && (
        <Button variant="secondary" data-testid="group-selection" onClick={onGroup}>
          Group
        </Button>
      )}
      {onUngroup && (
        <Button variant="secondary" data-testid="ungroup-selection" onClick={onUngroup}>
          Ungroup
        </Button>
      )}
      {onExtractToComposite && (
        <Button
          variant="secondary"
          data-testid="extract-to-composite"
          onClick={onExtractToComposite}
        >
          Extract to composite
        </Button>
      )}
    </div>
  );
}

export default SelectionToolbar;