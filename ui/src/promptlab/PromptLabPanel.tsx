import type { JSX } from "react";
import { useState } from "react";

import "./PromptLabPanel.css";
import { CompareGrid, type CompareGridLabel } from "./CompareGrid";
import { downloadDataset, labelRun } from "./exportDataset";
import { InputSetTable, type InputRow } from "./InputSetTable";
import { PromptEditor } from "./PromptEditor";
import type { PromptLabVariant } from "./providerModels";
import { runEval, type EvalRunRow } from "./runEval";
import { RunHistory, type RunHistoryEntry } from "./RunHistory";
import { extractVariablesFromTemplates } from "./variables";
import { VariantPicker } from "./VariantPicker";
import { newId } from "../store/ids";

export function PromptLabPanel(): JSX.Element {
  const [system, setSystem] = useState("");
  const [user, setUser] = useState("");
  const [selectedVariants, setSelectedVariants] = useState<PromptLabVariant[]>(
    [],
  );
  const [dataset, setDataset] = useState<InputRow[]>([]);
  const [rows, setRows] = useState<EvalRunRow[]>([]);
  const [labels, setLabels] = useState<CompareGridLabel[]>([]);
  const [history, setHistory] = useState<RunHistoryEntry[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const variables = extractVariablesFromTemplates([system, user]);

  async function handleRun(): Promise<void> {
    setRunning(true);
    setError(null);
    try {
      // A variable-less prompt has no rows to bind (InputSetTable hides its
      // add-row UI in that case, per its "single run mode" note) -- send one
      // empty-binding row so eval.run's `for row_id, row in enumerate(dataset)`
      // actually executes once instead of silently producing zero rows.
      const effectiveDataset = variables.length === 0 ? [{}] : dataset;
      const newRows = await runEval({
        system,
        user,
        variants: selectedVariants.map((v) => ({
          provider: v.provider,
          model: v.model,
        })),
        dataset: effectiveDataset,
      });
      setRows(newRows);
      setLabels([]);
      const entry: RunHistoryEntry = {
        id: newId("run"),
        timestamp: Date.now(),
        system,
        user,
        variants: selectedVariants.map((v) => ({
          provider: v.provider,
          model: v.model,
        })),
        dataset: effectiveDataset,
        rows: newRows,
        labels: [],
      };
      setHistory((prev) => [entry, ...prev]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }

  function handleSelectHistory(entry: RunHistoryEntry): void {
    setSystem(entry.system);
    setUser(entry.user);
    setSelectedVariants(
      entry.variants.map((v) => ({
        provider: v.provider,
        model: v.model,
        label: v.model,
      })),
    );
    setDataset(entry.dataset);
    setRows(entry.rows);
    setLabels(entry.labels);
  }

  async function handleExport(format: "eval_set" | "finetune"): Promise<void> {
    setError(null);
    try {
      const labeled = await labelRun(rows, labels);
      await downloadDataset(labeled, format);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div className="ef-promptlab-panel" data-testid="prompt-lab-panel">
      <PromptEditor
        system={system}
        user={user}
        onSystemChange={setSystem}
        onUserChange={setUser}
      />
      <VariantPicker
        selected={selectedVariants}
        onChange={setSelectedVariants}
      />
      <InputSetTable
        variables={variables}
        rows={dataset}
        onChange={setDataset}
      />
      <button
        type="button"
        onClick={handleRun}
        disabled={running}
        data-testid="prompt-lab-run"
      >
        {running ? "Running…" : "Run"}
      </button>
      {error !== null ? (
        <p className="ef-promptlab-panel__error" data-testid="prompt-lab-error">
          {error}
        </p>
      ) : null}
      <CompareGrid rows={rows} labels={labels} onLabelsChange={setLabels} />
      <div className="ef-promptlab-panel__export-actions">
        <button
          type="button"
          onClick={() => void handleExport("eval_set")}
          disabled={labels.length === 0}
          data-testid="prompt-lab-export-eval-set"
        >
          Export eval set
        </button>
        <button
          type="button"
          onClick={() => void handleExport("finetune")}
          disabled={labels.length === 0}
          data-testid="prompt-lab-export-finetune"
        >
          Export fine-tune set
        </button>
      </div>
      <RunHistory entries={history} onSelect={handleSelectHistory} />
    </div>
  );
}
