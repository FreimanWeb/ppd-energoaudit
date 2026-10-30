import { formatEfficiency, formatNumber } from "../format/number.mjs";

/**
 * @param {unknown} value
 * @param {unknown} reference
 * @param {"higher" | "lower"} direction Какое отклонение требует внимания.
 * @param {boolean} usable
 * @param {boolean} efficiency
 */
export function metricAssessment(value, reference, direction, usable = true, efficiency = false) {
  if (typeof value !== "number" || !Number.isFinite(value))
    return {tone: "neutral", caption: "Нет значения", reason: "Показатель отсутствует или не является конечным числом."};
  if (efficiency && (value < 0 || value > 1))
    return {tone: "bad", caption: "Физическая ошибка", reason: "КПД должен находиться между 0 и 100 %; проверьте исходные данные."};
  if (!usable)
    return {tone: "neutral", caption: "Данные непригодны", reason: "Качество исходного режима не позволяет оценить состояние оборудования."};
  if (typeof reference !== "number" || !Number.isFinite(reference))
    return {tone: "neutral", caption: "Нет сравнения", reason: "Нет подтверждённого эталона для оценки этого показателя."};
  const bad = direction === "higher" ? value > reference : value < reference;
  return {
    tone: bad ? "bad" : "good",
    caption: value === reference ? "На уровне сравнения" : value > reference ? "Выше сравнения" : "Ниже сравнения",
    reason: `Значение сравнивается с ${efficiency ? formatEfficiency(reference) : formatNumber(reference, 3)}. ${direction === "higher" ? "Превышение" : "Снижение"} требует внимания.`,
  };
}
