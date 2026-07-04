export interface PromptLabVariant {
  provider: string;
  model: string;
  label: string;
}

// The Prompt Lab's default selectable variants (Epic 9: Anthropic as the documented default
// provider). This is plain data, not derived from the live node catalog -- ef.llm.call's
// `model` param is a free-text field, not an enumerated catalog choice, so there is no
// generated source of truth to read this list from yet.
export const DEFAULT_VARIANTS: PromptLabVariant[] = [
  { provider: "anthropic", model: "claude-opus-4-8", label: "Claude Opus 4.8" },
  { provider: "anthropic", model: "claude-sonnet-5", label: "Claude Sonnet 5" },
  {
    provider: "anthropic",
    model: "claude-haiku-4-5-20251001",
    label: "Claude Haiku 4.5",
  },
];
