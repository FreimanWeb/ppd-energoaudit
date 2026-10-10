import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { DesignSystemPage } from "./DesignSystemPage";
import { calendarStatuses } from "./fixtures";
import "../style.css";
import "./catalogue.css";

// Изолированный каталог подставляет только собственный endpoint календаря.
const realFetch = window.fetch.bind(window);
window.fetch = (input, init) => {
  const url = new URL(input instanceof Request ? input.url : String(input), window.location.href);
  if (url.origin === window.location.origin && url.pathname === "/api/design-system/calendar") {
    const month = url.searchParams.get("month");
    return Promise.resolve(Response.json({ statuses: Object.fromEntries(
      Object.entries(calendarStatuses).filter(([date]) => date.startsWith(`${month}-`)),
    ) }));
  }
  return realFetch(input, init);
};

createRoot(document.getElementById("root")!).render(<StrictMode><DesignSystemPage /></StrictMode>);
