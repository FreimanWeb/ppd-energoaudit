import { useLayoutEffect, useRef, useState } from "react";

export function useHorizontalOverflow(content: unknown) {
  const container = useRef<HTMLDivElement>(null);
  const [scrollable, setScrollable] = useState(false);
  useLayoutEffect(() => {
    const element = container.current;
    if (!element) return;
    const measure = () => setScrollable(element.scrollWidth > element.clientWidth + 1);
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    if (element.firstElementChild) observer.observe(element.firstElementChild);
    measure();
    return () => observer.disconnect();
  }, [content]);
  return { container, scrollable };
}
