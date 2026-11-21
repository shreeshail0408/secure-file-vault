import { describe, expect, it, vi } from "vitest";
import { fakeServer } from "../test/fakeServer";
import { api, AUTH_LOGOUT_EVENT } from "./client";
import { getAccessToken, getRefreshToken, setTokens } from "./tokens";

const OK = { status: 200, data: { ok: true } };
const UNAUTHORIZED = { status: 401, data: { detail: "Token is invalid or expired" } };
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// A protected endpoint: 200 only with the NEW token.
const needsNewToken = (config) => (config.headers.Authorization === "Bearer new-access" ? OK : UNAUTHORIZED);

describe("request interceptor", () => {
  it("adds the access token to API requests", async () => {
    setTokens({ access: "abc", refresh: "r" });
    const server = fakeServer({ "GET /files/": OK });

    await api.get("/files/");

    expect(server.calls[0].auth).toBe("Bearer abc");
  });

  it("does not send a (possibly stale) token to login/register", async () => {
    setTokens({ access: "stale", refresh: "r" });
    const server = fakeServer({ "POST /auth/login/": OK, "POST /auth/register/": OK });

    await api.post("/auth/login/", {});
    await api.post("/auth/register/", {});

    expect(server.calls.map((call) => call.auth)).toEqual([undefined, undefined]);
  });
});

describe("refresh on 401", () => {
  it("refreshes ONCE for several simultaneous 401s and replays all of them", async () => {
    setTokens({ access: "old-access", refresh: "refresh-1" });
    const server = fakeServer({
      "GET /files/1/": needsNewToken,
      "GET /files/2/": needsNewToken,
      "GET /files/3/": needsNewToken,
      "POST /auth/refresh/": async () => {
        await wait(20); // slow refresh, so all three 401s arrive while it's in flight
        return { status: 200, data: { access: "new-access" } };
      },
    });

    const results = await Promise.all([api.get("/files/1/"), api.get("/files/2/"), api.get("/files/3/")]);

    expect(results.map((r) => r.status)).toEqual([200, 200, 200]);
    expect(server.count("POST /auth/refresh/")).toBe(1);
    expect(getAccessToken()).toBe("new-access");
    // each request: first try with the old token, replay with the new one
    expect(server.calls.filter((c) => c.key === "GET /files/1/").map((c) => c.auth))
      .toEqual(["Bearer old-access", "Bearer new-access"]);
  });

  it("a 401 arriving after another request already refreshed reuses the new token", async () => {
    setTokens({ access: "old-access", refresh: "refresh-1" });
    const server = fakeServer({
      "GET /fast/": needsNewToken,
      "GET /slow/": async (config) => {
        await wait(30); // answers 401 after the refresh has already finished
        return needsNewToken(config);
      },
      "POST /auth/refresh/": { status: 200, data: { access: "new-access" } },
    });

    await Promise.all([api.get("/fast/"), api.get("/slow/")]);

    expect(server.count("POST /auth/refresh/")).toBe(1);
  });

  it("stores a rotated refresh token if the server sends one", async () => {
    setTokens({ access: "old-access", refresh: "refresh-1" });
    fakeServer({
      "GET /files/": needsNewToken,
      "POST /auth/refresh/": { status: 200, data: { access: "new-access", refresh: "refresh-2" } },
    });

    await api.get("/files/");

    expect(getRefreshToken()).toBe("refresh-2");
  });

  it("when refresh fails: clears tokens, fires the logout event, rejects", async () => {
    setTokens({ access: "old-access", refresh: "expired-refresh" });
    const server = fakeServer({
      "GET /files/1/": UNAUTHORIZED,
      "GET /files/2/": UNAUTHORIZED,
      "POST /auth/refresh/": UNAUTHORIZED,
    });
    const onLogout = vi.fn();
    window.addEventListener(AUTH_LOGOUT_EVENT, onLogout);

    const results = await Promise.allSettled([api.get("/files/1/"), api.get("/files/2/")]);

    window.removeEventListener(AUTH_LOGOUT_EVENT, onLogout);
    expect(results.map((r) => r.status)).toEqual(["rejected", "rejected"]);
    expect(server.count("POST /auth/refresh/")).toBe(1);
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
    expect(onLogout).toHaveBeenCalled();
  });

  it("retries a request only once (no infinite loop)", async () => {
    setTokens({ access: "old-access", refresh: "refresh-1" });
    const server = fakeServer({
      "GET /always-401/": UNAUTHORIZED,
      "POST /auth/refresh/": { status: 200, data: { access: "new-access" } },
    });

    await expect(api.get("/always-401/")).rejects.toThrow();

    expect(server.count("GET /always-401/")).toBe(2);
    expect(server.count("POST /auth/refresh/")).toBe(1);
  });

  it("a 401 from login (wrong password) never triggers a refresh", async () => {
    setTokens({ access: "x", refresh: "refresh-1" });
    const server = fakeServer({ "POST /auth/login/": UNAUTHORIZED });

    await expect(api.post("/auth/login/", {})).rejects.toThrow();

    expect(server.count("POST /auth/refresh/")).toBe(0);
  });

  it("without a refresh token, a 401 is simply passed on", async () => {
    const server = fakeServer({ "GET /files/": UNAUTHORIZED });

    await expect(api.get("/files/")).rejects.toThrow();

    expect(server.count("POST /auth/refresh/")).toBe(0);
  });
});
