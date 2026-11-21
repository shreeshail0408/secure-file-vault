import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { getAccessToken } from "../api/tokens";
import { ALICE, deferred, EMPTY_PAGE, fakeServer, renderApp } from "../test/fakeServer";

const TOKENS = { status: 200, data: { access: "new-a", refresh: "new-r" } };

async function fillLogin(username = "alice", password = "Vault-Tiger-2026!") {
  if (username) await userEvent.type(await screen.findByLabelText("Username"), username);
  if (password) await userEvent.type(screen.getByLabelText("Password"), password);
  await userEvent.click(screen.getByRole("button", { name: "Log in" }));
}

describe("Login page", () => {
  it("logs in and shows the dashboard", async () => {
    fakeServer({ "POST /auth/login/": TOKENS, "GET /files/": EMPTY_PAGE, "GET /auth/me/": { status: 200, data: ALICE } });
    renderApp("/login");

    await fillLogin();

    expect(await screen.findByRole("heading", { name: "Files" })).toBeInTheDocument();
    expect(getAccessToken()).toBe("new-a");
  });

  it("shows the backend's field errors under each input", async () => {
    fakeServer({
      "POST /auth/login/": {
        status: 400,
        data: { username: ["This field may not be blank."], password: ["This field may not be blank."] },
      },
    });
    renderApp("/login");

    await fillLogin("", "");

    const username = screen.getByLabelText("Username");
    expect(username).toHaveClass("is-invalid");
    expect(username).toHaveAccessibleDescription("This field may not be blank.");
    expect(screen.getByLabelText("Password")).toHaveAccessibleDescription("This field may not be blank.");
  });

  it("shows the server's message for a wrong password (401)", async () => {
    fakeServer({
      "POST /auth/login/": { status: 401, data: { detail: "No active account found with the given credentials" } },
    });
    renderApp("/login");

    await fillLogin("alice", "wrong");

    expect(await screen.findByRole("alert")).toHaveTextContent("No active account found");
  });

  it("shows a friendly message when throttled (429)", async () => {
    fakeServer({ "POST /auth/login/": { status: 429, data: { detail: "Request was throttled." } } });
    renderApp("/login");

    await fillLogin();

    expect(await screen.findByRole("alert")).toHaveTextContent("Too many attempts, wait a minute");
  });

  it("disables the button while sending", async () => {
    const login = deferred();
    fakeServer({ "POST /auth/login/": login.promise });
    renderApp("/login");

    await fillLogin();

    const button = screen.getByRole("button", { name: /please wait/i });
    expect(button).toBeDisabled();

    await act(async () => login.resolve({ status: 401, data: { detail: "nope" } }));

    expect(screen.getByRole("button", { name: "Log in" })).toBeEnabled();
  });

  it("explains when the backend can't be reached", async () => {
    fakeServer({
      "POST /auth/login/": () => {
        throw Object.assign(new Error("Network Error"), { isAxiosError: true });
      },
    });
    renderApp("/login");

    await fillLogin();

    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot reach the server");
  });
});

describe("Register page", () => {
  async function fillRegister(server) {
    renderApp("/register");
    await userEvent.type(await screen.findByLabelText("Username"), "alice");
    await userEvent.type(screen.getByLabelText("Email"), "alice@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "12345");
    await userEvent.type(screen.getByLabelText("Confirm password"), "12345");
    await userEvent.click(screen.getByRole("button", { name: "Register" }));
    return server;
  }

  it("shows each field's errors from the backend", async () => {
    fakeServer({
      "POST /auth/register/": {
        status: 400,
        data: {
          username: ["This username is already taken."],
          password: ["This password is too short.", "This password is entirely numeric."],
        },
      },
    });

    await fillRegister();

    expect(screen.getByLabelText("Username")).toHaveAccessibleDescription("This username is already taken.");
    expect(screen.getByText("This password is too short.")).toBeInTheDocument();
    expect(screen.getByText("This password is entirely numeric.")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).not.toHaveClass("is-invalid");
  });

  it("registers, logs in automatically and opens the dashboard", async () => {
    const server = fakeServer({
      "POST /auth/register/": { status: 201, data: ALICE },
      "POST /auth/login/": TOKENS,
      "GET /files/": EMPTY_PAGE, "GET /auth/me/": { status: 200, data: ALICE },
    });

    await fillRegister(server);

    expect(await screen.findByRole("heading", { name: "Files" })).toBeInTheDocument();
    expect(server.count("POST /auth/login/")).toBe(1);
  });

  it("shows the friendly 429 message", async () => {
    fakeServer({ "POST /auth/register/": { status: 429, data: {} } });

    await fillRegister();

    expect(await screen.findByRole("alert")).toHaveTextContent("Too many attempts");
  });
});
