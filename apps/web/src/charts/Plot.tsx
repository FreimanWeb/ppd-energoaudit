import { Component, Suspense, lazy, useMemo, type ReactNode } from "react";
import { buildChartModel } from "./chartModel.mjs";
import type { ChartModel, Trace, Layout, TimeInteraction } from "./types";
export type { Trace, Layout } from "./types";

const ChartRenderer = lazy(() => import("./ChartRenderer"));

class ChartBoundary extends Component<{ children: ReactNode; model: ChartModel }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidUpdate(previous: { model: ChartModel }) {
    if (this.state.failed && previous.model !== this.props.model) this.setState({ failed: false });
  }
  render() {
    return this.state.failed ? <p className="notice error" role="alert">Не удалось отобразить график. Данные доступны в таблице.</p> : this.props.children;
  }
}

const emptyLayout: Layout = {};
export function Plot({ data, layout = emptyLayout, title, onSelect, timeInteraction }: {
  data: Trace[]; layout?: Layout; title: string; onSelect?: (label: string) => void; timeInteraction?: TimeInteraction;
}) {
  const model = useMemo(() => buildChartModel(data, layout, title), [data, layout, title]);
  return <div className="plot-wrap" role="group" aria-label={title}
    onPointerDownCapture={event => { event.currentTarget.dataset.input = "pointer"; }}
    onKeyDownCapture={event => { event.currentTarget.dataset.input = "keyboard"; }}
    onKeyUpCapture={event => { event.currentTarget.dataset.input = "keyboard"; }}>
    <ChartBoundary model={model}>
      <Suspense fallback={<p role="status" className="muted">Загружаем график…</p>}>
        <ChartRenderer model={model} onSelect={onSelect} timeInteraction={timeInteraction} />
      </Suspense>
    </ChartBoundary>
  </div>;
}
