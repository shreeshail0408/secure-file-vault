// JWT storage in localStorage. Simple, survives page reloads.
// Trade-off (for the review): any script on the page could read it, so the app
// must not render untrusted HTML. An httpOnly cookie would avoid that.

const ACCESS = "vault.access";
const REFRESH = "vault.refresh";

export const getAccessToken = () => localStorage.getItem(ACCESS);
export const getRefreshToken = () => localStorage.getItem(REFRESH);

export function setTokens({ access, refresh }) {
  if (access) localStorage.setItem(ACCESS, access);
  if (refresh) localStorage.setItem(REFRESH, refresh);
}

export function clearTokens() {
  localStorage.removeItem(ACCESS);
  localStorage.removeItem(REFRESH);
}
