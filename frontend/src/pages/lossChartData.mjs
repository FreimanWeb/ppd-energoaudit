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
      connector: { line: { color: "#d5dedb" } },
      decreasing: { marker: { color: "#c76e62" } },
      increasing: { marker: { color: "#c58b25" } },
      totals: { marker: { color: "#1f4e4a" } },
    },
    sankey: {
      type: "sankey",
      arrangement: "snap",
      node: {
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
    shares: items.map((item, i) => ({
      type: "bar",
      orientation: "h",
      name: item.name,
      x: [item.share * 100],
      y: [""],
      text: [`${item.name} ${Math.round(item.share * 100)} %`],
      textposition: "inside",
      marker: {
        color:
          item.category === "полезная"
            ? "#1f4e4a"
            : ["#c76e62", "#c58b25", "#d6a681", "#8b9892"][i % 4],
      },
    })),
  };
}
