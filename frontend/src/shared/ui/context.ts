export type PageProps = {
  inspectionKey?: string;
  objectId: string;
  aggregateId: string;
  day: string;
  timestamp: string;
  source: "telemetry" | "field_trip";
  audit?: {
    audit: { trace: Record<string, unknown> };
    quality: { status: string };
  };
};

export const contextBody = (
  p: PageProps,
  extra: Record<string, unknown> = {},
) =>
  JSON.stringify({
    source: p.source,
    ...(p.source === "telemetry" ? { day: p.day, timestamp: p.timestamp } : {}),
    ...extra,
  });
