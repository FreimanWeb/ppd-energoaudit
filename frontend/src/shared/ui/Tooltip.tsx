import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import "./tooltip.css";

export function Tooltip({ label, content, children }: {
  label: string;
  content: ReactNode;
  children?: ReactNode;
}) {
  const id = useId();
  const button = useRef<HTMLButtonElement>(null);
  const tip = useRef<HTMLDivElement>(null);
  const timer = useRef<number | undefined>(undefined);
  const [open, setOpen] = useState(false);
  const [present, setPresent] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [position, setPosition] = useState({ left: 12, top: 12 });
  const cancelHide = () => window.clearTimeout(timer.current);
  const show = () => { cancelHide(); setOpen(true); };
  const close = () => {
    cancelHide();
    if (!open) return;
    if (tip.current) {
      const style = window.getComputedStyle(tip.current);
      tip.current.style.setProperty("--tooltip-opacity", style.opacity);
      tip.current.style.setProperty("--tooltip-transform", style.transform);
    }
    setOpen(false);
    setPinned(false);
  };
  const hide = () => {
    cancelHide();
    if (!pinned && document.activeElement !== button.current)
      timer.current = window.setTimeout(close, 140);
  };
  useEffect(() => {
    if (open) { setPresent(true); return; }
    if (!present) return;
    const delay = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 140;
    const removal = window.setTimeout(() => setPresent(false), delay);
    return () => window.clearTimeout(removal);
  }, [open, present]);
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const anchor = button.current?.getBoundingClientRect();
      const bounds = tip.current?.getBoundingClientRect();
      if (!anchor || !bounds) return;
      const left = Math.max(12, Math.min(anchor.left, window.innerWidth - bounds.width - 12));
      const below = anchor.bottom + 8;
      const top = below + bounds.height <= window.innerHeight - 12
        ? below : Math.max(12, anchor.top - bounds.height - 8);
      setPosition({ left, top });
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open, content]);
  useEffect(() => {
    if (!open) return;
    const key = (event: KeyboardEvent) => { if (event.key === "Escape" || event.key === "Tab") close(); };
    const outside = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!button.current?.contains(target) && !tip.current?.contains(target)) close();
    };
    document.addEventListener("keydown", key);
    document.addEventListener("pointerdown", outside);
    return () => {
      cancelHide();
      document.removeEventListener("keydown", key);
      document.removeEventListener("pointerdown", outside);
    };
  }, [open]);
  return <>
    <button
      ref={button}
      type="button"
      className={children === undefined ? "tooltip-trigger" : "tooltip-value"}
      aria-label={`Пояснение: ${label}`}
      aria-describedby={open ? id : undefined}
      onPointerEnter={event => { if (event.pointerType !== "touch") show(); }}
      onPointerLeave={hide}
      onFocus={show}
      onBlur={() => { if (!pinned) close(); }}
      onClick={() => { if (pinned) close(); else { show(); setPinned(true); } }}
    >{children ?? (
      <svg aria-hidden="true" width="14" height="14" viewBox="0 0 416.979 416.979" fill="currentColor">
        <path d="M356.004,61.156c-81.37-81.47-213.377-81.551-294.848-0.182c-81.47,81.371-81.552,213.379-0.181,294.85c81.369,81.47,213.378,81.551,294.849,0.181C437.293,274.636,437.375,142.626,356.004,61.156z M237.6,340.786c0,3.217-2.607,5.822-5.822,5.822h-46.576c-3.215,0-5.822-2.605-5.822-5.822V167.885c0-3.217,2.607-5.822,5.822-5.822h46.576c3.215,0,5.822,2.604,5.822,5.822V340.786z M208.49,137.901c-18.618,0-33.766-15.146-33.766-33.765c0-18.617,15.147-33.766,33.766-33.766c18.619,0,33.766,15.148,33.766,33.766C242.256,122.755,227.107,137.901,208.49,137.901z" />
      </svg>
    )}</button>
    {(open || present) && createPortal(
      <div id={id} ref={tip} role="tooltip" aria-hidden={!open} data-state={open ? "open" : "closing"} className="explanation-tooltip" style={position}
        onPointerEnter={show} onPointerLeave={hide}>
        {content}
      </div>, document.body,
    )}
  </>;
}
