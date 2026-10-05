import { useEffect, useRef, useState } from "react";
import type { Data, Layout } from "plotly.js";

// Большой renderer загружается только при первом открытии графика.
let renderer: Promise<typeof import("plotly.js")> | undefined;
export type Trace = Partial<Data>;
export function Plot({
  data,
  layout = {},
  title,
  onSelect,
}: {
  data: Trace[];
  layout?: Partial<Layout>;
  title: string;
  onSelect?: (label: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    const target = container.current!;
    let plot: typeof import("plotly.js") | undefined;
    renderer ??= import("plotly.js-dist-min").then((module) => module.default);
    renderer
      .then(async (loaded) => {
        if (!active) return;
        plot = loaded;
        const element = await loaded.react(
          target,
          data as Data[],
          {
            autosize: true,
            height: 360,
            paper_bgcolor: "white",
            plot_bgcolor: "white",
            font: {
              family: "Inter, Segoe UI, Arial",
              color: "#33413b",
              size: 12,
            },
            margin: { l: 65, r: 25, t: 25, b: 55 },
            legend: { orientation: "h", y: -0.18 },
            xaxis: { gridcolor: "#eef1ef" },
            yaxis: { gridcolor: "#eef1ef" },
            ...layout,
          },
          {
            responsive: true,
            displaylogo: false,
            modeBarButtonsToRemove: ["lasso2d", "select2d"],
          },
        );
        if (active && onSelect)
          element.on("plotly_click", (event) => {
            const point = event.points[0];
            let label = point?.customdata ?? point?.text;
            // В общей вершине Plotly может выбрать конец ребра вместо узла.
            if (point && typeof label !== "string") {
              for (const trace of data) {
                if (!("x" in trace) || !("y" in trace) || !("customdata" in trace))
                  continue;
                const { x, y, customdata } = trace;
                if (!Array.isArray(x) || !Array.isArray(y) || !Array.isArray(customdata))
                  continue;
                const index = x.findIndex((value, i) => value === point.x && y[i] === point.y);
                if (index >= 0 && typeof customdata[index] === "string") {
                  label = customdata[index];
                  break;
                }
              }
            }
            if (typeof label === "string") onSelect(label);
          });
      })
      .catch(() => {
        if (active)
          setError("Не удалось отобразить график. Данные доступны в таблице.");
      });
    const resize = new ResizeObserver(() => {
      if (plot && active) void plot.Plots.resize(target);
    });
    resize.observe(target);
    return () => {
      active = false;
      resize.disconnect();
      plot?.purge(target);
    };
  }, [data, layout, onSelect]);
  return (
    <div className="plot-wrap" role="group" aria-label={title}>
      <div ref={container} />
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
