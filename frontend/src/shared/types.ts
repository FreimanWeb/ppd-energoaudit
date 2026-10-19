export type Plant = {
  code: string;
  name: string;
  ngdu_name: string;
  water_type: string;
  branch: string;
  is_example: boolean;
  has_telemetry?: boolean;
};
export type Aggregate = {
  code: string;
  role: string;
  pump_model: string | null;
  has_telemetry: boolean;
};
export type Dates = { dates: string[]; default_date: string | null };
export type Snapshot = {
  timestamp: string;
  p_in_mpa: number;
  p_out_mpa: number;
  p_bg_mpa: number | null;
  power_kw: number;
  power_age_seconds?: number | null;
  p_bg_age_seconds?: number | null;
};
export type Equipment = {
  id: string;
  type: string;
  x: number;
  y: number;
  label?: string;
  sub?: string;
  agg?: string;
  hint?: string;
};
export type Topology = {
  title: string;
  source: string;
  is_typical: boolean;
  nodes: Equipment[];
  edges: { from: string; to: string; kind?: string }[];
};
export type Audit = {
  pump_assessment: {name: string; tone: string};
  source: "telemetry" | "field_trip";
  audit: {
    object_id: string;
    object_name: string;
    aggregate_id: string;
    branch: string;
    pump_kind: string;
    metrics: Record<string, number | null>;
    trace: Record<string, unknown>;
  };
  snapshot: Snapshot | null;
  quality: {
    status: "ready" | "assumptions" | "unfit";
    issues: { code: string; message: string; severity: string }[];
    basis: Record<string, string>;
  };
  sources: Record<string, string>;
  scope: {
    annual_runtime_hours: number;
    annual_runtime_is_assumed: boolean;
    daily_kpi_is_fact: boolean;
  };
  regime: {
    p_in: number;
    p_out: number;
    p_bg: number | null;
    q_day: number | null;
    t: number | null;
    w: number | null;
    t_year: number | null;
    rho: number;
    nu?: number | null;
    q_fact: number | null;
    p_electric: number | null;
  };
  passport: {
    id: string;
    role: string;
    vfd: boolean;
    runtime_total_h?: number | null;
    pump: {
      model: string | null;
      kind: string;
      q_nom: number | null;
      h_nom: number | null;
      eta_nom: number | null;
      power_nom: number | null;
      n_rpm: number | null;
      curve_qh: [number, number][];
      curve_qeta: [number, number][];
    };
    motor: {
      model: string | null;
      p_nom: number | null;
      eta_nom: number | null;
      cos_phi: number | null;
      voltage_kv: number | null;
      synchronous: boolean;
    };
    transmission: {
      model: string | null;
      ratio: number | null;
      efficiency: number;
    };
  };
  annual_summary: Record<string, number | null>;
  tariff: number;
  tariff_warning?: string | null;
  target_sec: number | null;
  losses: {
    name: string;
    power_kw: number;
    share: number;
    annual_kwh: number | null;
    annual_rub: number | null;
    category: string;
  }[];
};
