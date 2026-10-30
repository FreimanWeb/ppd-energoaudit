import type { ChartModel, TimeInteraction } from "./types";
import { CartesianChart } from "./CartesianChart";
import { FlowChart } from "./FlowChart";
import { GaugeChart } from "./GaugeChart";
import { NetworkChart } from "./NetworkChart";
import "./charts.css";
export default function ChartRenderer({
  model,
  onSelect,
  timeInteraction,
}: {
  model: ChartModel;
  onSelect?: (id: string) => void;
  timeInteraction?: TimeInteraction;
}) {
  switch (model.kind) {
    case "cartesian":
      return <CartesianChart model={model} onSelect={onSelect} timeInteraction={timeInteraction} />;
    case "sankey":
      return <FlowChart model={model} onSelect={onSelect} />;
    case "gauge":
      return <GaugeChart model={model} />;
    case "network":
      return <NetworkChart model={model} onSelect={onSelect} />;
    case "empty":
      return (
        <p className="notice" role="status">
          {model.message}
        </p>
      );
  }
}
