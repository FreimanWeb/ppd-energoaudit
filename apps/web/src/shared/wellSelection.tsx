import { useSyncExternalStore } from "react";
import { LinkButton } from "./ui/Button";
import "./wellSelection.css";

function subscribe(onChange: () => void) {
  window.addEventListener("popstate", onChange);
  window.addEventListener("hashchange", onChange);
  window.addEventListener("ppd:well-selection", onChange);
  return () => {
    window.removeEventListener("popstate", onChange);
    window.removeEventListener("hashchange", onChange);
    window.removeEventListener("ppd:well-selection", onChange);
  };
}

export function wellHref(section: string, code: string) {
  const url = new URL(window.location.href);
  if (code) url.searchParams.set("well", code);
  else url.searchParams.delete("well");
  url.hash = section;
  return url.href;
}

export function setWellSelection(code: string) {
  history.replaceState(null, "", wellHref(location.hash.slice(1), code));
  window.dispatchEvent(new Event("ppd:well-selection"));
}

export function useWellSelection() {
  return useSyncExternalStore(subscribe, () => new URL(location.href).searchParams.get("well") ?? "");
}

export function WellLinks({ code }: { code: string }) {
  return <span className="well-context-links">
    <LinkButton href={wellHref("well-history", code)}>История и ГДИ</LinkButton>{" "}
    <LinkButton href={wellHref("crm-wells", code)}>Прогноз по скважине · CRM</LinkButton>
  </span>;
}
