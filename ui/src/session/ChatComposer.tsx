import { useEffect, useRef, useState, type JSX } from "react";
import type { Persona } from "./usePersonas";

export interface ChatComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  personas: Persona[];
  placeholder?: string;
  rows?: number;
  disabled?: boolean;
  "data-testid": string;
}

const PALETTE_PERSONA_SLUGS = ["data_scientist", "researcher", "ml_engineer"];

export function ChatComposer(props: ChatComposerProps): JSX.Element {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [dismissed, setDismissed] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);

  const eligiblePersonas = props.personas.filter((p) =>
    PALETTE_PERSONA_SLUGS.includes(p.slug),
  );

  const paletteTriggered =
    props.value.startsWith("/") && !/\s/.test(props.value) && !dismissed;

  const filteredPersonas = paletteTriggered
    ? eligiblePersonas.filter((p) => {
        const command = `/${p.slug.replace(/_/g, "-")}`;
        return command.startsWith(props.value.toLowerCase());
      })
    : [];

  const paletteOpen = paletteTriggered && filteredPersonas.length > 0;

  useEffect(() => {
    setActiveIndex((prev) =>
      Math.min(prev, Math.max(0, filteredPersonas.length - 1)),
    );
  }, [filteredPersonas.length]);

  const selectPersona = (persona: Persona): void => {
    const command = `/${persona.slug.replace(/_/g, "-")}`;
    props.onChange(command + " ");
    textareaRef.current?.focus();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>): void => {
    if (paletteOpen) {
      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setActiveIndex(
            (prev) => (prev + 1) % filteredPersonas.length,
          );
          return;
        case "ArrowUp":
          e.preventDefault();
          setActiveIndex(
            (prev) =>
              (prev - 1 + filteredPersonas.length) % filteredPersonas.length,
          );
          return;
        case "Enter":
          if (!e.shiftKey) {
            e.preventDefault();
            selectPersona(filteredPersonas[activeIndex]);
          }
          return;
        case "Tab":
          e.preventDefault();
          selectPersona(filteredPersonas[activeIndex]);
          return;
        case "Escape":
          e.preventDefault();
          setDismissed(true);
          return;
      }
    } else {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        props.onSubmit();
      }
    }
  };

  return (
    <div style={{ position: "relative", flex: 1 }}>
      <textarea
        ref={textareaRef}
        data-testid={props["data-testid"]}
        value={props.value}
        onChange={(e) => {
          setDismissed(false);
          props.onChange(e.target.value);
        }}
        onKeyDown={handleKeyDown}
        placeholder={props.placeholder}
        rows={props.rows}
        disabled={props.disabled}
        style={{ flex: 1 }}
      />
      {paletteOpen ? (
        <div
          data-testid={`${props["data-testid"]}-palette`}
          style={{
            position: "absolute",
            bottom: "100%",
            left: 0,
            marginBottom: "var(--space-1)",
            zIndex: 20,
            minWidth: 160,
            background: "var(--glass-bg)",
            border: "1px solid var(--glass-border)",
            borderRadius: "var(--radius-md)",
            boxShadow: "var(--shadow-2)",
            padding: "var(--space-1)",
            display: "flex",
            flexDirection: "column",
          }}
        >
          {filteredPersonas.map((persona, i) => {
            const command = `/${persona.slug.replace(/_/g, "-")}`;
            return (
              <button
                key={persona.slug}
                type="button"
                data-testid={`${props["data-testid"]}-palette-option-${persona.slug}`}
                onClick={() => selectPersona(persona)}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "flex-start",
                  width: "100%",
                  padding: "var(--space-1) var(--space-2)",
                  border: "none",
                  background:
                    i === activeIndex
                      ? "var(--surface-3)"
                      : "transparent",
                  color: "var(--text-primary)",
                  fontFamily: "var(--font-ui)",
                  fontSize: "var(--text-sm)",
                  textAlign: "left",
                  cursor: "pointer",
                  borderRadius: "var(--radius-sm)",
                  whiteSpace: "nowrap",
                  lineHeight: 1.4,
                  transition:
                    "background var(--motion-fast) var(--motion-ease)",
                }}
              >
                <span style={{ fontWeight: 600 }}>{command}</span>
                <span style={{ color: "var(--text-secondary)", fontSize: "var(--text-sm)" }}>
                  {persona.description}
                </span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
