import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { familyMeta } from "../theme/family";
import { LensBar } from "./LensBar";

describe("LensBar", () => {
  it("renders nothing with no families", () => {
    const { container } = render(<LensBar families={[]} active={[]} onToggle={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders a chip per family with its label", () => {
    render(<LensBar families={["ml", "data"]} active={[]} onToggle={vi.fn()} />);
    expect(screen.getByTestId("lens-chip-ml")).toBeTruthy();
    expect(screen.getByTestId("lens-chip-data")).toBeTruthy();
    expect(screen.getByText(familyMeta("ml").label)).toBeTruthy();
  });

  it("marks the active chip as pressed", () => {
    render(<LensBar families={["ml", "data"]} active={["ml"]} onToggle={vi.fn()} />);
    expect(screen.getByTestId("lens-chip-ml").getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByTestId("lens-chip-data").getAttribute("aria-pressed")).toBe("false");
  });

  it("calls onToggle with the family when clicked", () => {
    const onToggle = vi.fn();
    render(<LensBar families={["ml"]} active={[]} onToggle={onToggle} />);
    fireEvent.click(screen.getByTestId("lens-chip-ml"));
    expect(onToggle).toHaveBeenCalledWith("ml");
  });
});
