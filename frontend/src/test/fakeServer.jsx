// Test helpers: a fake backend plugged into axios, and a way to render the app.
//
// fakeServer({ "GET /auth/me/": { status: 200, data: {...} } }) replaces axios's
// network layer (the "adapter"), so the real interceptors in client.js still run.
// A route can also be a function (config) => ({ status, data }) or a Promise of it.

import { render } from "@testing-library/react";
import { AxiosError } from "axios";
import { MemoryRouter } from "react-router-dom";
import App from "../App";
import { api, refreshClient } from "../api/client";
import { AuthProvider } from "../auth/AuthContext";

export function fakeServer(routes) {
  const calls = [];

  async function adapter(config) {
    const key = `${config.method.toUpperCase()} ${config.url}`;
    calls.push({ key, auth: config.headers.Authorization });
    const route = routes[key];
    if (!route) throw new Error(`fakeServer: no route for ${key}`);

    const { status, data } = typeof route === "function" ? await route(config) : await route;
    const response = { status, data, headers: {}, config, statusText: String(status) };
    if (status >= 200 && status < 300) return response;
    throw new AxiosError(`Request failed with status ${status}`, "ERR_BAD_RESPONSE", config, null, response);
  }

  api.defaults.adapter = adapter;
  refreshClient.defaults.adapter = adapter;
  return {
    calls,
    count: (key) => calls.filter((call) => call.key === key).length,
  };
}

// A promise you resolve later, to test "while the request is still pending".
export function deferred() {
  let resolve;
  const promise = new Promise((r) => (resolve = r));
  return { promise, resolve };
}

export function renderApp(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}

export const ALICE = { id: 1, username: "alice", email: "alice@example.com", is_staff: false };
