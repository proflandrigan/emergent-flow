import type { JSX } from "react";

import "./VariantPicker.css";
import { DEFAULT_VARIANTS, type PromptLabVariant } from "./providerModels";

export interface VariantPickerProps {
  selected: PromptLabVariant[];
  onChange: (variants: PromptLabVariant[]) => void;
}

function variantKey(v: Pick<PromptLabVariant, "provider" | "model">): string {
  return `${v.provider}:${v.model}`;
}

export function VariantPicker({
  selected,
  onChange,
}: VariantPickerProps): JSX.Element {
  const selectedKeys = new Set(selected.map(variantKey));

  function toggle(variant: PromptLabVariant): void {
    const key = variantKey(variant);
    if (selectedKeys.has(key)) {
      onChange(selected.filter((v) => variantKey(v) !== key));
    } else {
      onChange([...selected, variant]);
    }
  }

  return (
    <fieldset className="ef-promptlab-variants" data-testid="variant-picker">
      <legend>Variants</legend>
      {DEFAULT_VARIANTS.map((variant) => {
        const key = variantKey(variant);
        return (
          <label key={key} className="ef-promptlab-variants__option">
            <input
              type="checkbox"
              checked={selectedKeys.has(key)}
              onChange={() => toggle(variant)}
              data-testid={`variant-checkbox-${key}`}
            />
            {variant.label}
          </label>
        );
      })}
    </fieldset>
  );
}
