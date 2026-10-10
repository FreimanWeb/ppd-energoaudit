import { Table } from "../../shared/ui/Table";

const columns = [
  { key: "parameter", label: "Параметр" },
  { key: "value", label: "Значение", align: "end" as const },
];

export function Dictionary({ values }: { values: Record<string, unknown> }) {
  return <Table rows={Object.entries(values).map(([parameter, value]) => ({ parameter, value }))} columns={columns} />;
}
