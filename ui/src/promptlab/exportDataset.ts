import type { CompareGridLabel } from "./CompareGrid";
import { postJson } from "./httpJson";
import type { EvalRunRow } from "./runEval";

export type ExportFormat = "eval_set" | "finetune";

// POSTs /eval/label to merge `labels` onto `results` (Epic 9 Story 6's ef.eval.label, via the
// server), returning the labeled rows as plain JSON records.
export async function labelRun(
  results: EvalRunRow[],
  labels: CompareGridLabel[],
): Promise<Record<string, unknown>[]> {
  const res = await postJson("/eval/label", { results, labels });
  const body = await res.json();
  return body.labeled;
}

// POSTs /export/eval_set or /export/finetune with the labeled rows, then triggers a browser
// file download of the returned JSONL bytes (Epic 9 Story 8's "Save dataset" action).
export async function downloadDataset(
  labeledRows: Record<string, unknown>[],
  format: ExportFormat,
): Promise<void> {
  const path = format === "eval_set" ? "/export/eval_set" : "/export/finetune";
  const filename = format === "eval_set" ? "eval_set.jsonl" : "finetune.jsonl";

  const res = await postJson(path, { rows: labeledRows });

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}
