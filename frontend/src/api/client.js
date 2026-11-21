import axios from "axios";
import { clearTokens, getAccessToken, getRefreshToken, setTokens } from "./tokens";

export const API_URL = import.meta.env.VITE_API_URL;

// Fired when the session can't be saved (refresh failed). AuthContext listens
// and sends the user to /login. An event keeps this file free of React code.
export const AUTH_LOGOUT_EVENT = "auth:logout";

// The app's axios instance: every request goes through the two interceptors below.
export const api = axios.create({ baseURL: API_URL });

// A separate plain instance for the refresh call, so it never goes through the
// interceptors (a failing refresh must not trigger another refresh).
export const refreshClient = axios.create({ baseURL: API_URL });

// Login/register/refresh handle their own 401s (e.g. wrong password).
const AUTH_URLS = ["/auth/login/", "/auth/register/", "/auth/refresh/"];
const isAuthUrl = (url = "") => AUTH_URLS.some((path) => url.endsWith(path));

// --- 1. Attach the access token -----------------------------------------------
api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token && !isAuthUrl(config.url)) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// --- 2. On 401: refresh the access token ONCE, then replay the request ----------
//
// If 5 requests fail with 401 at the same time, they all wait for the SAME
// refresh promise, so the server sees one refresh call, and all 5 are replayed.
let refreshPromise = null;

function refreshAccessToken() {
  if (!refreshPromise) {
    refreshPromise = refreshClient
      .post("/auth/refresh/", { refresh: getRefreshToken() })
      .then((response) => {
        setTokens(response.data); // {access} (+ {refresh} if the server rotates it)
        return response.data.access;
      })
      .finally(() => {
        refreshPromise = null; // the next expiry starts a new refresh
      });
  }
  return refreshPromise;
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const request = error.config;
    const shouldRefresh =
      error.response?.status === 401 &&
      request &&
      !request._retried && // only one retry per request, never a loop
      !isAuthUrl(request.url) &&
      getRefreshToken();

    if (!shouldRefresh) {
      return Promise.reject(error);
    }
    request._retried = true;

    try {
      // If another request already refreshed while this one was in flight,
      // just reuse the new token instead of refreshing again.
      const sentToken = request.headers.Authorization?.replace("Bearer ", "");
      const current = getAccessToken();
      const token = current && current !== sentToken ? current : await refreshAccessToken();

      request.headers.Authorization = `Bearer ${token}`;
      return api(request);
    } catch {
      // Refresh token expired or invalid: the session is over.
      clearTokens();
      window.dispatchEvent(new Event(AUTH_LOGOUT_EVENT));
      return Promise.reject(error);
    }
  },
);
