export function Status({
  loading,
  error,
  data,
  empty = "Нет данных для выбранного периода.",
}: {
  loading?: boolean;
  error?: string;
  data?: unknown;
  empty?: string;
}) {
  return error ? (
    <p className="notice error" role="alert">
      {error}
    </p>
  ) : loading ? (
    <p className="notice" role="status">
      Загружаем данные…
    </p>
  ) : data === undefined ? (
    <p className="notice">{empty}</p>
  ) : null;
}
