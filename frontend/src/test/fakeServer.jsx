// Test helpers: a fake backend plugged into axios, and a way to render the app.
//
// fakeServer({ "GET /auth/me/": { status: 200, data: {...} } }) replaces axios's
// network layer (the "adapter"), so the real interceptors in client.js still run.
// A route can also be a function (config) => ({ status, data, headers }) or a Promise of it.

import { render } from "@testing-library/react";
import { AxiosError } from "axios";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import App from "../App";
import { api, refreshClient } from "../api/client";
import { AuthProvider } from "../auth/AuthContext";

export function fakeServer(routes) {
  const calls = [];

  async function adapter(config) {
    const key = `${config.method.toUpperCase()} ${config.url}`;
    calls.push({ key, auth: config.headers.Authorization, params: config.params || {} });
    const route = routes[key];
    if (!route) throw new Error(`fakeServer: no route for ${key}`);

    const { status, data, headers = {} } = typeof route === "function" ? await route(config) : await route;
    const response = { status, data, headers, config, statusText: String(status) };
    if (status >= 200 && status < 300) return response;
    throw new AxiosError(`Request failed with status ${status}`, "ERR_BAD_RESPONSE", config, null, response);
  }

  api.defaults.adapter = adapter;
  refreshClient.defaults.adapter = adapter;
  return {
    calls,
    count: (key) => calls.filter((call) => call.key === key).length,
    last: (key) => calls.filter((call) => call.key === key).at(-1),
  };
}

// A promise you resolve later, to test "while the request is still pending".
export function deferred() {
  let resolve;
  const promise = new Promise((r) => (resolve = r));
  return { promise, resolve };
}

// Shows the current URL and offers a Back button, so tests can check the query string.
// (Test-only file, never hot-reloaded, so the fast-refresh lint rule doesn't apply.)
// oxlint-disable-next-line react/only-export-components
function LocationProbe() {
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <div hidden>
      <output data-testid="location">{location.pathname + location.search}</output>
      <button type="button" onClick={() => navigate(-1)}>test-back</button>
    </div>
  );
}

// entries: one path, or a history list (the last one is the current page).
export function renderApp(entries = "/") {
  const history = Array.isArray(entries) ? entries : [entries];
  return render(
    <MemoryRouter initialEntries={history} initialIndex={history.length - 1}>
      <AuthProvider>
        <App />
        <LocationProbe />
      </AuthProvider>
    </MemoryRouter>,
  );
}

export const ALICE = { id: 1, username: "alice", email: "alice@example.com", is_staff: false };
export const EMPTY_PAGE = { status: 200, data: { count: 0, next: null, previous: null, results: [] } };
