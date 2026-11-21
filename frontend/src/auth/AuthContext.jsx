import { useEffect, useState } from "react";
import { api, AUTH_LOGOUT_EVENT } from "../api/client";
import { clearTokens, getAccessToken, getRefreshToken, setTokens } from "../api/tokens";
import { AuthContext } from "./useAuth";

const hasSavedTokens = () => Boolean(getAccessToken() || getRefreshToken());

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  // With saved tokens we must ask the server before deciding, so start in
  // "loading": protected pages show a spinner instead of flashing the login page.
  const [loading, setLoading] = useState(hasSavedTokens);

  // On start: if we have tokens, ask the server who we are.
  useEffect(() => {
    if (!hasSavedTokens()) return;
    api
      .get("/auth/me/") // an expired access token is refreshed automatically by client.js
      .then((response) => setUser(response.data))
      .catch(() => clearTokens())
      .finally(() => setLoading(false));
  }, []);

  // client.js fires this when the refresh token is no longer valid.
  useEffect(() => {
    const onLogout = () => setUser(null);
    window.addEventListener(AUTH_LOGOUT_EVENT, onLogout);
    return () => window.removeEventListener(AUTH_LOGOUT_EVENT, onLogout);
  }, []);

  async function login(username, password) {
    const response = await api.post("/auth/login/", { username, password });
    setTokens(response.data);
    const me = await api.get("/auth/me/");
    setUser(me.data);
  }

  function logout() {
    clearTokens();
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
