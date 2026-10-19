const iconPaths = {
  "machine-losses": "M3 3v18h18 M6 6h3v12H6z M11 6h3v4h-3z M16 10h3v4h-3z",
  "machine-block": "M3 6h18v15H3z M7 6V3h10v3 M6 11h4v6H6z M14 11h4v6h-4z",
  pipelines: "M2 8h8v8h12 M2 12h4v8h16 M10 6v8 M18 14v8",
  wells: "M8 3h8 M12 3v18 M7 7h10 M5 21h14 M9 7l-3 14 M15 7l3 14",
  portfolio: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z M6 6h1 M17 6h1",
  timeline: "M3 3v18h18 M6 15l4-5 4 3 6-7 M6 19h14",
  overview: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  snapshot: "M4 17a9 9 0 1 1 16 0 M12 12l4-4 M6 12h1 M12 6v1 M17 12h1 M8 20h8",
  "telemetry-data": "M3 4h18v16H3z M6 8h12 M6 12h3m3 0h6 M6 16h12",
  telemetry: "M3 12h4l3-7 4 14 3-7h4",
  scheme: "M3 9h5v6H3z M16 3h5v6h-5z M16 15h5v6h-5z M8 12h4V6h4 M12 12v6h4",
  forecast: "M3 3v18h18 M6 16l5-6 4 3 6-8 M16 5h5v5",
  crm: "M12 3 2 8l10 5 10-5z M2 12l10 5 10-5 M2 16l10 5 10-5",
  "crm-wells": "M12 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6 M5 22a3 3 0 1 0 0-6 3 3 0 0 0 0 6 M19 22a3 3 0 1 0 0-6 3 3 0 0 0 0 6 M12 8v4 M5 16v-4h14v4",
  losses: "M13 2 4 14h7l-1 8 10-13h-7z",
  "working-point": "M12 2v4 M12 18v4 M2 12h4 M18 12h4 M20 12a8 8 0 1 1-16 0 8 8 0 0 1 16 0 M14 12a2 2 0 1 1-4 0 2 2 0 0 1 4 0",
  measures: "M9 3h6v3h-6z M9 5H5v16h14V5h-4 M8 12l2 2 5-5 M8 18h7",
  network: "M3 12h5 M8 12l5-6h4 M8 12l5 6h4 M17 6h4 M17 18h4 M13 12h8",
  sources: "M20 6c0 2-16 2-16 0s16-2 16 0 M4 6v12c0 4 16 4 16 0V6 M4 12c0 4 16 4 16 0",
  formulas: "M19 4H5l7 8-7 8h14",
  onboarding: "M3 8l9-5 9 5-9 5z M3 8v11l9 4V13 M21 8v5 M17 18h6 M20 15v6",
  menu: "M4 6h16 M4 12h16 M4 18h16",
};
export function Icon({ name }: { name: string }) {
  return (
    <svg
      className="ui-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path
        d={iconPaths[name as keyof typeof iconPaths] || iconPaths.overview}
      />
    </svg>
  );
}
