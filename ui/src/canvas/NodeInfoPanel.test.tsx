import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import type { CatalogNode } from "../catalog/types";
import { NodeInfoPanel } from "./NodeInfoPanel";

const fixture: CatalogNode = {
  type: "test.do_something",
  version: 1,
  family: "test",
  label: "Do Something",
  description: "A test node that does something useful.",
  paradigm: "FUNCTIONAL",
  ports: [
    {
      name: "input_data",
      direction: "in",
      data_type: "any",
      cardinality: "one",
      required: true,
      label: "Input Data",
      help: "The data to process.",
    },
    {
      name: "output_data",
      direction: "out",
      data_type: "any",
      cardinality: "one",
      label: "Output Data",
    },
  ],
  params: [
    {
      name: "threshold",
      type_token: "float",
      default: 0.5,
      required: false,
      label: "Threshold",
      help: "Sensitivity threshold for the operation.",
    },
    {
      name: "mode",
      type_token: "string",
      default: "auto",
      required: true,
      label: "Mode",
    },
  ],
};

describe("NodeInfoPanel", () => {
  test("renders label, type, description, and family", () => {
    render(<NodeInfoPanel node={fixture} />);

    expect(screen.getByText("Do Something")).toBeInTheDocument();
    expect(screen.getByText("test.do_something")).toBeInTheDocument();
    expect(
      screen.getByText("A test node that does something useful."),
    ).toBeInTheDocument();
    expect(screen.getByText("test")).toBeInTheDocument();
  });

  test("renders port names and their help text", () => {
    render(<NodeInfoPanel node={fixture} />);

    expect(screen.getByText("Input Data")).toBeInTheDocument();
    expect(screen.getByText("(in)")).toBeInTheDocument();
    expect(
      screen.getByText("The data to process."),
    ).toBeInTheDocument();

    expect(screen.getByText("Output Data")).toBeInTheDocument();
    expect(screen.getByText("(out)")).toBeInTheDocument();
  });

  test("renders param names and their help text", () => {
    render(<NodeInfoPanel node={fixture} />);

    expect(screen.getByText("Threshold")).toBeInTheDocument();
    expect(
      screen.getByText("Sensitivity threshold for the operation."),
    ).toBeInTheDocument();

    expect(screen.getByText("Mode")).toBeInTheDocument();
  });

  test("renders section headings for ports and params", () => {
    render(<NodeInfoPanel node={fixture} />);

    expect(screen.getByText("Ports")).toBeInTheDocument();
    expect(screen.getByText("Params")).toBeInTheDocument();
  });

  test("renders the panel with the correct testid", () => {
    render(<NodeInfoPanel node={fixture} />);

    expect(screen.getByTestId("node-info-panel")).toBeInTheDocument();
  });
});
