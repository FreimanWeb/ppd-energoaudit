import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Auth } from "./features/auth/Auth";
import { App } from "./app/App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Auth>{(logout) => <App logout={logout} />}</Auth>
  </StrictMode>,
);
