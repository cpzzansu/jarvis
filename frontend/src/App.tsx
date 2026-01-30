import { useEffect, useState } from "react";
import AgentChat from "./components/AgentChat";
import LoginPage from "./components/LoginPage";
import { logoutApi, meApi } from "./lib/api";

export default function App() {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);

  useEffect(() => {
    meApi().then((r) => setAuthenticated(r != null));
  }, []);

  async function handleLogout() {
    await logoutApi();
    setAuthenticated(false);
  }

  if (authenticated === null) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
        Loading...
      </div>
    );
  }
  if (!authenticated) {
    return <LoginPage onSuccess={() => setAuthenticated(true)} />;
  }
  return <AgentChat onLogout={handleLogout} />;
}
