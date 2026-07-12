import {
  Database,
  Filter,
  Sigma,
  Brain,
  Network,
  FileText,
  Wand2,
  MessageSquare,
  type LucideIcon,
} from "lucide-react";

export interface FamilyMeta {
  label: string;
  color: string;
  soft: string;
  Icon: LucideIcon;
}

export const FAMILY: Record<string, FamilyMeta> = {
  data: {
    label: "Data",
    color: "var(--fam-data)",
    soft: "var(--fam-data-soft)",
    Icon: Database,
  },
  clean: {
    label: "Clean",
    color: "var(--fam-clean)",
    soft: "var(--fam-clean-soft)",
    Icon: Filter,
  },
  stats: {
    label: "Statistics",
    color: "var(--fam-stats)",
    soft: "var(--fam-stats-soft)",
    Icon: Sigma,
  },
  ml: {
    label: "Machine Learning",
    color: "var(--fam-ml)",
    soft: "var(--fam-ml-soft)",
    Icon: Brain,
  },
  nn: {
    label: "Neural Nets",
    color: "var(--fam-nn)",
    soft: "var(--fam-nn-soft)",
    Icon: Network,
  },
  reports: {
    label: "Reports",
    color: "var(--fam-reports)",
    soft: "var(--fam-reports-soft)",
    Icon: FileText,
  },
  transform: {
    label: "Transform",
    color: "var(--fam-transform)",
    soft: "var(--fam-transform-soft)",
    Icon: Wand2,
  },
  notes: {
    label: "Notes",
    color: "var(--fam-notes)",
    soft: "var(--fam-notes-soft)",
    Icon: MessageSquare,
  },
};

export const familyMeta = (f: string): FamilyMeta =>
  FAMILY[f] ?? {
    label: f,
    color: "var(--text-secondary)",
    soft: "var(--surface-2)",
    Icon: FileText,
  };
