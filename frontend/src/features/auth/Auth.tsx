import { useEffect, useState, type ReactNode } from "react";
import { useResource } from "../../shared/api";
import { Button } from "../../shared/ui/Button";
type Session = { authentication_required: boolean; authenticated: boolean };
export function Auth({
  children,
}: {
  children: (logout: (() => void) | undefined) => ReactNode;
}) {
  const [epoch, setEpoch] = useState(0),
    [password, setPassword] = useState(""),
    [error, setError] = useState(""),
    [pending, setPending] = useState(false);
  const session = useResource<Session>(`/auth/session?check=${epoch}`);
  useEffect(() => {
    const expired = () => setEpoch((e) => e + 1);
    window.addEventListener("ppd:unauthorized", expired);
    return () => window.removeEventListener("ppd:unauthorized", expired);
  }, []);
  async function login(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      const data = await response.json();
      if (!response.ok)
        throw new Error(
          typeof data.detail === "string" ? data.detail : "Не удалось войти.",
        );
      setPassword("");
      setEpoch((e) => e + 1);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Не удалось войти.");
    } finally {
      setPending(false);
    }
  }
  async function logout() {
    try {
      const response = await fetch("/api/auth/logout", { method: "POST" });
      if (!response.ok) throw new Error("Не удалось выйти.");
      setEpoch((e) => e + 1);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Не удалось выйти.");
    }
  }
  if (session.data?.authenticated)
    return (
      <>
        {error && (
          <p className="notice error" role="alert">
            {error}
          </p>
        )}
        {children(session.data.authentication_required ? logout : undefined)}
      </>
    );
  return (
    <div className="login-shell">
      <form className="login-card" onSubmit={login}>
        <span className="brand-mark">ППД</span>
        <h1>Энергоаудит ППД</h1>
        <p>Войдите, чтобы анализировать оборудование и режимы работы.</p>
        {session.loading ? (
          <p role="status">Проверяем доступ…</p>
        ) : session.error ? (
          <p role="alert">{session.error}</p>
        ) : (
          <>
            <label>
              Пароль
              <input
                aria-label="Пароль"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                maxLength={4096}
              />
            </label>
            <Button type="submit" loading={pending}>
              {pending ? "Входим…" : "Войти"}
            </Button>
          </>
        )}
        {error && (
          <p className="notice error" role="alert">
            {error}
          </p>
        )}
      </form>
    </div>
  );
}
