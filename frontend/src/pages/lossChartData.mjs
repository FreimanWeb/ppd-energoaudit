/** @param {number} input @param {{name:string,power_kw:number,share:number,category:string}[]} items */
export function lossChartData(input, items) {
  const useful = items.find((x) => x.category === "полезная");
  const losses = items.filter((x) => x.category === "потеря");
  const flows = items.filter((x) => x.power_kw > 0);
  return {
    waterfall: {
      type: "waterfall",
      orientation: "v",
      measure: ["absolute", ...losses.map(() => "relative"), "absolute"],
      x: [
        "Подведённая мощность",
        ...losses.map((x) => x.name),
        "Полезная мощность",
      ],
      y: [input, ...losses.map((x) => -x.power_kw), useful?.power_kw ?? 0],
      tooltip: [{ value: input, unit: "кВт", share: input > 0 ? 1 : undefined },
        ...losses.map(x => ({ value: x.power_kw, unit: "кВт", share: x.share, selection: x.name })),
        { value: useful?.power_kw ?? 0, unit: "кВт", share: useful?.share, selection: useful?.name }],
      connector: { line: { color: "#d5dedb" } },
      decreasing: { marker: { color: "#c76e62" } },
      increasing: { marker: { color: "#c58b25" } },
      totals: { marker: { color: "#1f4e4a" } },
    },
    sankey: {
      type: "sankey",
      arrangement: "snap",
      node: {
        tooltip: [{ value: input, unit: "кВт", share: input > 0 ? 1 : undefined }, ...flows.map(x => ({ value: x.power_kw, unit: "кВт", share: x.share, selection: x.name }))],
        label: ["Подведённая мощность", ...flows.map((x) => x.name)],
        color: [
          "#426b80",
          ...flows.map((x) =>
            x.category === "полезная" ? "#1f4e4a" : "#c76e62",
          ),
        ],
        pad: 25,
        thickness: 20,
      },
      link: {
        tooltip: flows.map(x => ({ value: x.power_kw, unit: "кВт", share: x.share, selection: x.name })),
        source: flows.map(() => 0),
        target: flows.map((_, i) => i + 1),
        value: flows.map((x) => x.power_kw),
        color: flows.map((x) =>
          x.category === "полезная"
            ? "rgba(31,78,74,.35)"
            : "rgba(199,110,98,.3)",
        ),
      },
    },
  };
}
