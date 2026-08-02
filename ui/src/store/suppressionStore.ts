// Suppression of validity findings, stored BESIDE the graph (never on it -- ADR 0019
// discipline, same as provenance): a finding is suppressed per (rule_id, node_id) with an
// optional human reason. Persisted to localStorage so a suppression survives a reload, and
// keyed per (rule_id, node_id) so the same rule on a different node is unaffected.
// ef.validate itself never sees this -- the canvas filters findings client-side.

import { create } from "zustand";

const STORAGE_KEY = "ef-suppressions";

export type SuppressionMap = Record<string, string>; // "rule_id::node_id" -> reason

function readStored(): SuppressionMap {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (typeof parsed !== "object" || parsed === null) return {};
    return parsed as SuppressionMap;
  } catch {
    return {};
  }
}

export interface SuppressionStore {
  suppressions: SuppressionMap;
  isSuppressed: (ruleId: string | null | undefined, nodeId: string | null | undefined) => boolean;
  suppress: (ruleId: string, nodeId: string, reason: string) => void;
  unsuppress: (ruleId: string, nodeId: string) => void;
  clear: () => void;
}

const keyFor = (ruleId: string, nodeId: string) => `${ruleId}::${nodeId}`;

export const useSuppressionStore = create<SuppressionStore>((set, get) => ({
  suppressions: readStored(),

  isSuppressed(ruleId, nodeId) {
    if (!ruleId || !nodeId) return false;
    return keyFor(ruleId, nodeId) in get().suppressions;
  },

  suppress(ruleId, nodeId, reason) {
    const next = { ...get().suppressions, [keyFor(ruleId, nodeId)]: reason };
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // storage full or unavailable -- suppression still applies for this session
    }
    set({ suppressions: next });
  },

  unsuppress(ruleId, nodeId) {
    const rest = { ...get().suppressions };
    delete rest[keyFor(ruleId, nodeId)];
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(rest));
    } catch {
      // ignore
    }
    set({ suppressions: rest });
  },

  clear() {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
    set({ suppressions: {} });
  },
}));
