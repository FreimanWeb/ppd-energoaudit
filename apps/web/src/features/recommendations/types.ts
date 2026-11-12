import type { DiagnosticReport } from "../../shared/types";

export type AlgorithmRow = { id: number; deviation: string; cause: string; action: string; responsible: string; note: string };
export type Defects = {
  source: string;
  element: string;
  total: number;
  first: string | null;
  last: string | null;
  high: number;
  by_kind: { kind: string; count: number; last: string | null; algorithm: AlgorithmRow[] }[];
  recent: { number: string; date: string | null; defect: string; kind: string; cause: string; criticality: string; status: string }[];
};
export type MotorBenchmark = {
  group: string; item: string; power_kw: number; current_brand: string; best_brand: string;
  alternatives: string[]; current_efficiency_pct: string; best_efficiency_pct: string;
  passport_efficiency_pct: number | null; gain_pct: number | null;
};
export type PumpBenchmark = {
  daily_flow_m3: number; class: string; flow_unit: string; current_pumps: string; current_sec: number;
  current_efficiency: string; efficient_pumps: string; efficient_sec: number; efficient_efficiency: string;
  sec_fact: number; gap_to_efficient: number;
};
export type Recommendations = {
  pump_model: string | null;
  motor_model: string | null;
  values: Record<string, number | null>;
  diagnostics: DiagnosticReport;
  pump_benchmark: PumpBenchmark | null;
  motor_benchmark: MotorBenchmark | null;
  pump_range: { found: boolean; note?: string; q_min_m3h?: number; q_max_m3h?: number; q_in_range?: boolean; size?: string; head_m?: number };
  defects: Defects | null;
  sources: string[];
  quality: { status: string; issues: string[] };
};
