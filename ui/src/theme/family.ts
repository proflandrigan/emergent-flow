import {
  Database,
  Filter,
  Sigma,
  Brain,
  Network,
  FileText,
  Wand2,
  MessageSquare,
  BarChart3,
  TrendingUp,
  Sparkles,
  Microscope,
  Bot,
  ClipboardCheck,
  Binary,
  FlaskConical,
  Code2,
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
  viz: {
    label: "Visualization",
    color: "var(--fam-viz)",
    soft: "var(--fam-viz-soft)",
    Icon: BarChart3,
  },
  timeseries: {
    label: "Time Series",
    color: "var(--fam-timeseries)",
    soft: "var(--fam-timeseries-soft)",
    Icon: TrendingUp,
  },
  recommend: {
    label: "Recommenders",
    color: "var(--fam-recommend)",
    soft: "var(--fam-recommend-soft)",
    Icon: Sparkles,
  },
  explain: {
    label: "Model Explainability",
    color: "var(--fam-explain)",
    soft: "var(--fam-explain-soft)",
    Icon: Microscope,
  },
  llm: {
    label: "LLM",
    color: "var(--fam-llm)",
    soft: "var(--fam-llm-soft)",
    Icon: Bot,
  },
  eval: {
    label: "Evals",
    color: "var(--fam-eval)",
    soft: "var(--fam-eval-soft)",
    Icon: ClipboardCheck,
  },
  embed: {
    label: "Embeddings",
    color: "var(--fam-embed)",
    soft: "var(--fam-embed-soft)",
    Icon: Binary,
  },
  research: {
    label: "Research",
    color: "var(--fam-research)",
    soft: "var(--fam-research-soft)",
    Icon: FlaskConical,
  },
  script: {
    label: "Custom Code",
    color: "var(--fam-script)",
    soft: "var(--fam-script-soft)",
    Icon: Code2,
  },
};

// Fallback for families the UI does not know about (plugin-contributed nodes). Every
// family in the shipped catalog is expected to have a real entry above -- see the
// coverage guard in ui/src/palette/groupNodesBySection.test.ts.
export const familyMeta = (f: string): FamilyMeta =>
  FAMILY[f] ?? {
    label: f,
    color: "var(--text-secondary)",
    soft: "var(--surface-2)",
    Icon: FileText,
  };
