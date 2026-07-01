import type { JSX } from "react";
import "./Menu.css";

export interface MenuItem {
  label: string;
  onSelect: () => void;
  disabled?: boolean;
}

export interface MenuProps {
  items: MenuItem[];
  "aria-label"?: string;
}

export function Menu({
  items,
  "aria-label": ariaLabel,
}: MenuProps): JSX.Element {
  return (
    <div className="ef-menu glass-strong" role="menu" aria-label={ariaLabel}>
      {items.map((item, i) => (
        <button
          key={i}
          className="ef-menu__item"
          role="menuitem"
          disabled={item.disabled}
          onClick={() => item.onSelect()}
          type="button"
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
