import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { getAccessToken, getRefreshToken, setTokens } from "../api/tokens";
import { ALICE, deferred, EMPTY_PAGE, fakeServer, renderApp } from "../test/fakeServer";

describe("protected routes", () => {
  it("shows a spinner (not the login page) while /auth/me/ is loading", async () => {
    setTokens({ access: "a", refresh: "r" });
    const me = deferred();
    fakeServer({ "GET /files/": EMPTY_PAGE, "GET /auth/me/": me.promise });

    renderApp("/");

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Log in" })).not.toBeInTheDocument();

    await act(async () => me.resolve({ status: 200, data: ALICE }));

    expect(await screen.findByRole("heading", { name: "Files" })).toBeInTheDocument();
    expect(screen.queryByText("Loading...")).not.toBeInTheDocument(); // the auth spinner is gone
  });

  it("without tokens goes straight to the login page (no /me call)", async () => {
    const server = fakeServer({});

    renderApp("/");

    expect(await screen.findByRole("button", { name: "Log in" })).toBeInTheDocument();
    expect(server.calls).toEqual([]);
  });

  it("expired session (me 401 + refresh 401) ends on the login page with tokens cleared", async () => {
    setTokens({ access: "old", refresh: "expired" });
    fakeServer({
      "GET /files/": EMPTY_PAGE, "GET /auth/me/": { status: 401, data: {} },
      "POST /auth/refresh/": { status: 401, data: {} },
    });

    renderApp("/");

    expect(await screen.findByRole("button", { name: "Log in" })).toBeInTheDocument();
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });

  it("logged-in users visiting /login are sent to the dashboard", async () => {
    setTokens({ access: "a", refresh: "r" });
    fakeServer({ "GET /files/": EMPTY_PAGE, "GET /auth/me/": { status: 200, data: ALICE } });

    renderApp("/login");

    expect(await screen.findByRole("heading", { name: "Files" })).toBeInTheDocument();
  });

  it("shows the Admin badge only for staff users", async () => {
    setTokens({ access: "a", refresh: "r" });
    fakeServer({ "GET /files/": EMPTY_PAGE, "GET /auth/me/": { status: 200, data: { ...ALICE, is_staff: true } } });

    renderApp("/");

    expect(await screen.findByText("Admin")).toBeInTheDocument();
  });
});

describe("logout", () => {
  it("clears both tokens and shows the login page", async () => {
    setTokens({ access: "a", refresh: "r" });
    fakeServer({ "GET /files/": EMPTY_PAGE, "GET /auth/me/": { status: 200, data: ALICE } });
    renderApp("/");

    await userEvent.click(await screen.findByRole("button", { name: "Log out" }));

    expect(await screen.findByRole("button", { name: "Log in" })).toBeInTheDocument();
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });
});
