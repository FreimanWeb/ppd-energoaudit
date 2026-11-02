import { useEffect, useState } from "react";

type Resource<T> = { key: string; resourceKey: string; data?: T; error?: string };
export const segment = encodeURIComponent;

const INVALIDATE_EVENT = "ppd:invalidate";

/** Сбросить выборку всех useResource после изменения данных на сервере
 *  (сохранение паспорта, ручной замер): каждый вид перезапросит свои данные. */
export function invalidateResources() {
  window.dispatchEvent(new Event(INVALIDATE_EVENT));
}

export function useResource<T>(url: string | null, body?: string, retainOnRefresh = false) {
  const key = url ? `${url}:${body ?? ""}` : "";
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    const bump = () => setNonce((value) => value + 1);
    window.addEventListener(INVALIDATE_EVENT, bump);
    return () => window.removeEventListener(INVALIDATE_EVENT, bump);
  }, []);
  const requestKey = `${key}#${nonce}`;
  const [result, setResult] = useState<Resource<T>>({ key: "", resourceKey: "" });
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
          if (response.status === 401)
            window.dispatchEvent(new Event("ppd:unauthorized"));
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
        if (!controller.signal.aborted) setResult({ key: requestKey, resourceKey: key, data });
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setResult(previous => ({ key: requestKey, resourceKey: key, error: error.message,
            data: retainOnRefresh && previous.resourceKey === key ? previous.data : undefined }));
      });
    return () => controller.abort();
  }, [url, body, requestKey, key, retainOnRefresh]);
  // Смена выбора никогда не показывает прежние данные. Справочники могут
  // удерживать текущий выбор при обновлении; результаты расчётов — нет.
  const current: Pick<Resource<T>, "data" | "error"> = result.key === requestKey ? result
    : retainOnRefresh && result.resourceKey === key ? {data: result.data} : {};
  return {
    data: current.data,
    error: current.error,
    loading: Boolean(url && !current.data && !current.error),
  };
}
