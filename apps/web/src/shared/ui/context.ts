import type { AnalysisContext, EquipmentData } from "../types";

export type PageProps = {
  inspectionKey?: string;
  objectId: string;
  aggregateId: string;
  day: string;
  timestamp: string;
  source: "telemetry" | "field_trip";
  measurementId?: number | null;
  equipmentOverride?: EquipmentData | null;
  hasNetwork?: boolean;
  isExample?: boolean;
  selectionPending?: boolean;
  audit?: {
    audit: { trace: Record<string, unknown> };
    quality: { status: string };
    analysis_context?: AnalysisContext;
  };
};

/** Тело запросов расчётных представлений: единый контекст источника режима,
 *  выбранного ручного замера и временного сценария оборудования. */
export const contextBody = (
  p: PageProps,
  extra: Record<string, unknown> = {},
) =>
  JSON.stringify({
    source: p.source,
    ...(p.source === "telemetry" ? { day: p.day, timestamp: p.timestamp } : {}),
    ...(p.source === "field_trip" && p.measurementId ? { measurement_id: p.measurementId } : {}),
    ...(p.equipmentOverride ? { equipment_override: p.equipmentOverride } : {}),
    ...extra,
  });
