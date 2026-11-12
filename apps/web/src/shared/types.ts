export type Plant = {
  code: string;
  name: string;
  ngdu_name: string;
  water_type: string;
  branch: string;
  is_example: boolean;
  has_telemetry?: boolean;
  has_network?: boolean;
};
export type Aggregate = {
  code: string;
  role: string;
  pump_model: string | null;
  has_telemetry: boolean;
  technical_place_code: string;
  technical_place_name: string;
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
export type DiagnosticRule = {
  id: string;
  title: string;
  category: "data_check" | "operating_deviation" | "inspection";
  status: "triggered" | "clear" | "insufficient_data" | "pending_confirmation" | "not_applicable";
  condition: string;
  evidence: { key: string; label: string; value: number | null; unit: string; basis: string }[];
  reason: string;
  action: string;
  source: { artifact_id: string; file: string; sha256: string; sheet: string; cells: string };
};
export type DiagnosticReport = {
  object_id: string;
  aggregate_id: string;
  pump_model: string;
  binding_status: "matched" | "pending_confirmation" | "model_mismatch" | "not_applicable";
  note: string;
  rules: DiagnosticRule[];
};
export type PumpCurveSource = {
  kind: "manufacturer" | "engineering" | "experimental" | "unverified";
  reference: string;
  model: string | null;
  speed_rpm: number | null;
  frequency_hz: number | null;
  verified: boolean;
  note: string;
};
export type PumpSpec = {
  model: string;
  kind: string;
  q_nom: number | null;
  h_nom: number | null;
  eta_nom: number | null;
  power_nom: number | null;
  n_rpm: number | null;
  curve_qh: [number, number][];
  curve_qeta: [number, number][];
  curve_source: PumpCurveSource | null;
};
export type MotorSpec = {
  model: string;
  synchronous: boolean;
  p_nom: number | null;
  eta_nom: number | null;
  cos_phi: number | null;
  voltage_kv: number | null;
  i_nom: number | null;
  n_rpm: number | null;
};
export type TransmissionSpec = {
  model: string | null;
  ratio: number | null;
  efficiency: number | null;
};
export type EquipmentData = {
  pump: PumpSpec;
  motor: MotorSpec;
  transmission: TransmissionSpec;
  vfd: boolean;
};
export type EquipmentHistory = {
  id: number;
  valid_from: string;
  valid_to: string | null;
  source: string | null;
  comment: string | null;
  author: string | null;
  revision: string;
  action: "insert" | "supersede" | "baseline";
  recorded_at: string | null;
  superseded?: EquipmentData;
  equipment?: EquipmentData;
};
export type JournalEntry = {
  id: number;
  component: "pump" | "motor" | "transmission" | "vfd";
  effective_at: string;
  recorded_at: string;
  /** Только явно заявленные пользователем поля канонических ключей. */
  changes: Record<string, unknown>;
  /** Поля, автоматически сброшенные при замене узла; генерируются сервером, не редактируются. */
  resets: Record<string, unknown>;
  reason: "repair" | "replacement" | "passport" | "inspection" | "correction";
  evidence: "documented" | "estimate";
  source: string;
  author: string;
  comment: string | null;
  supersedes_id: number | null;
  superseded_by: number | null;
};
export type EquipmentParameter = {
  key: string;
  component: JournalEntry["component"];
  name: string;
  symbol: string;
  unit: string;
  kind: "text" | "number" | "bool" | "select" | "curve_qh" | "curve_qeta" | "curve_source";
  minimum?: number;
  maximum?: number;
  exclusive_minimum?: boolean;
  options?: {value: string; label: string}[];
};
export type EquipmentJournalResponse = {
  revision: string;
  items: JournalEntry[];
  legacy_history: EquipmentHistory[];
  parameters: EquipmentParameter[];
};
export type EquipmentResponse = {
  passport_id: number | null;
  revision: string;
  valid_from: string | null;
  valid_to: string | null;
  equipment: EquipmentData;
  provenance: {
    source: string;
    comment: string;
    author: string;
    recorded_at: string;
    confirmed_fields?: string[];
    field_sources?: Record<string, {
      source: string; comment: string; author: string; recorded_at: string;
      effective_at?: string | null;
      evidence?: "documented" | "estimate";
      reason?: string;
      journal_id?: number | null;
      reset?: boolean;
    }>;
  } | null;
  history: EquipmentHistory[];
};
export type RegimeMeasurementData = {
  measured_at?: string | null;
  rho: number | null;
  p_in: number | null;
  p_out: number | null;
  p_bg?: number | null;
  q_day?: number | null;
  t?: number | null;
  w?: number | null;
  q_fact?: number | null;
  p_electric?: number | null;
  power_daily_reported?: number | null;
  nu?: number | null;
  t_year?: number | null;
};
export type ManualMeasurement = {
  id: number;
  measured_at: string;
  source: string;
  comment: string;
  author: string;
  regime: RegimeMeasurementData;
};
export type AnalysisContext = {
  source?: "telemetry" | "field_trip";
  day?: string | null;
  timestamp?: string | null;
  measurement_id?: number | null;
  equipment_override?: EquipmentData | null;
};
export type Requirement = {
  key: string;
  label: string;
  status: "missing" | "pending_confirmation" | "conflict" | "assumed" | "ready";
  value: number | string | boolean | null;
  unit: string;
  reason: string;
  affects: string[];
  action: "equipment" | "measurement" | "network" | "review";
  action_label: string;
};
export type LossComponent = {
  key: string;
  name: string;
  power_kw: number | null;
  share_pct: number | null;
  annual_kwh: number | null;
  annual_rub: number | null;
  origin: "measured" | "calculated" | "assumed" | "unavailable";
  formula: string;
  substitution: string;
  formula_latex: string;
  substitution_latex: string | null;
  basis: string;
  inputs: { key: string; label: string; value: number | string | boolean | null; unit: string; origin: string; source: string }[];
};
export type LossDetail = {
  key: string;
  title: string;
  boundary: string;
  status: "ready" | "partial" | "unavailable";
  total_kw: number | null;
  unallocated_kw?: number | null;
  balance_residual_kw?: number | null;
  input_kw: number | null;
  output_kw: number | null;
  annual_runtime_hours: number;
  annual_runtime_is_assumed: boolean;
  tariff: number;
  annual_kwh: number | null;
  annual_rub: number | null;
  components: LossComponent[];
  requirements: Requirement[];
  notes: string[];
};
export type Audit = {
  pump_assessment: {name: string; tone: string};
  diagnostics: DiagnosticReport;
  source: "telemetry" | "field_trip";
  analysis_context?: AnalysisContext;
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
    measured_at: string | null;
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
    power_daily_reported: number | null;
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
