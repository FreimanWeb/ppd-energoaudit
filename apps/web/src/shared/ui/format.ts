export { formatNumber as fmt } from "../format/number.mjs";

export const dateShift = (day: string, delta: number) => {
  if (!day) return "";
  const date = new Date(`${day}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + delta);
  return date.toISOString().slice(0, 10);
};
