import { useEffect, useState } from "react";

type Resource<T> = { key: string; data?: T; error?: string };
export const segment = encodeURIComponent;

export function useResource<T>(url: string | null, body?: string) {
  const key = url ? `${url}:${body ?? ""}` : "";
  const [result, setResult] = useState<Resource<T>>({ key: "" });
  useEffect(() => {
    if (!url) return;
    const controller = new AbortController();
    fetch(`/api${url}`, {
      signal: controller.signal,
      ...(body
        ? {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body,
          }
        : {}),
    })
      .then(async (response) => {
        if (!response.ok) {
          const detail = await response.json().catch(() => null);
          throw new Error(
            typeof detail?.detail === "string"
              ? detail.detail
              : "Не удалось загрузить данные. Попробуйте обновить страницу.",
          );
        }
        return response.json() as Promise<T>;
      })
      .then((data) => {
        if (!controller.signal.aborted) setResult({ key, data });
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setResult({ key, error: error.message });
      });
    return () => controller.abort();
  }, [url, body, key]);
  // Ключ не даёт показать результат предыдущего выбора до запуска нового effect.
  const current = result.key === key ? result : { key };
  return {
    data: current.data,
    error: current.error,
    loading: Boolean(url && !current.data && !current.error),
  };
}
