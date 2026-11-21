import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { setTokens } from "../api/tokens";
import { ALICE, deferred, EMPTY_PAGE, fakeServer, renderApp } from "../test/fakeServer";

// 45 files → 3 pages of 20. Alice owns the even ids.
const ALL_FILES = Array.from({ length: 45 }, (_, i) => ({
  id: i + 1,
  original_name: i % 2 ? `photo_${i + 1}.png` : `invoice_${i + 1}.pdf`,
  file_type: i % 2 ? "image" : "pdf",
  mime_type: i % 2 ? "image/png" : "application/pdf",
  size: (i + 1) * 100 * 1024,
  uploaded_by: i % 2 ? "bob" : "alice",
  can_edit: !(i % 2),
  created_at: "2026-11-21T10:30:00Z",
  updated_at: "2026-11-21T10:30:00Z",
}));

// Behaves like the real API: search, type filter, pages of 20, 404 for a bad page.
function filesEndpoint(config) {
  const { search = "", type = "", page = 1 } = config.params || {};
  const matches = ALL_FILES.filter(
    (f) => f.original_name.toLowerCase().includes(search.toLowerCase()) && (!type || f.file_type === type),
  );
  const results = matches.slice((page - 1) * 20, page * 20);
  if (page > 1 && results.length === 0) return { status: 404, data: { detail: "Invalid page." } };
  return { status: 200, data: { count: matches.length, next: null, previous: null, results } };
}

function startDashboard(path = "/", { user = ALICE, routes = {} } = {}) {
  setTokens({ access: "a", refresh: "r" });
  const server = fakeServer({ "GET /auth/me/": { status: 200, data: user }, "GET /files/": filesEndpoint, ...routes });
  renderApp(path);
  return server;
}

const location = () => screen.getByTestId("location").textContent;
const cards = () => screen.queryAllByTestId("file-card");
const cardFor = (name) => screen.getByText(name).closest("[data-testid=file-card]");

describe("file grid", () => {
  it("shows a loading skeleton, then one card per file with details", async () => {
    startDashboard();

    expect(await screen.findByRole("status", { name: "Loading files" })).toBeInTheDocument();
    expect(await screen.findByText("invoice_1.pdf")).toBeInTheDocument();
    expect(cards()).toHaveLength(20);

    const card = within(cardFor("invoice_1.pdf"));
    expect(card.getByText("PDF")).toBeInTheDocument();
    expect(card.getByText("100.0 KB")).toBeInTheDocument();
    expect(card.getByText("21 Nov 2026")).toBeInTheDocument();
    expect(card.getByText("alice")).toBeInTheDocument();
    expect(within(cardFor("photo_12.png")).getByText("1.2 MB")).toBeInTheDocument();
    expect(within(cardFor("photo_12.png")).getByText("Image")).toBeInTheDocument();
  });

  it("shows Edit/Delete only on files the user can edit", async () => {
    startDashboard();
    await screen.findByText("invoice_1.pdf");

    expect(within(cardFor("invoice_1.pdf")).getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(within(cardFor("invoice_1.pdf")).getByRole("button", { name: "Delete" })).toBeInTheDocument();
    expect(within(cardFor("photo_2.png")).queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(within(cardFor("photo_2.png")).queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
  });

  it("shows 'Export all' only to admins", async () => {
    startDashboard();
    await screen.findByText("invoice_1.pdf");
    expect(screen.queryByRole("button", { name: /export all/i })).not.toBeInTheDocument();
  });

  it("admin 'Export all' downloads the ZIP with the server's filename", async () => {
    const server = startDashboard("/", {
      user: { ...ALICE, is_staff: true },
      routes: {
        "GET /files/export/": {
          status: 200, data: new Blob(["PK"]),
          headers: { "content-disposition": 'attachment; filename="vault-export-2026-11-21.zip"' },
        },
      },
    });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function () {
      click.savedAs = this.download;
    });

    await userEvent.click(await screen.findByRole("button", { name: /export all/i }));

    await waitFor(() => expect(click.savedAs).toBe("vault-export-2026-11-21.zip"));
    expect(server.count("GET /files/export/")).toBe(1);
    click.mockRestore();
  });
});

describe("search, filter and the URL", () => {
  it("search is debounced, goes into the URL and resets to page 1", async () => {
    const server = startDashboard("/?page=2");
    await screen.findByText("invoice_21.pdf");

    await userEvent.type(screen.getByLabelText("Search files"), "photo_1");

    // One request for the whole word, not one per keystroke.
    await waitFor(() => expect(location()).toBe("/?search=photo_1"));
    await screen.findByText("photo_10.png");
    const searches = server.calls.filter((c) => c.key === "GET /files/" && c.params.search);
    expect(searches.map((c) => c.params)).toEqual([{ search: "photo_1", type: undefined, page: undefined }]);
  });

  it("type filter goes into the URL and resets to page 1", async () => {
    const server = startDashboard("/?page=2");
    await screen.findByText("invoice_21.pdf");

    await userEvent.selectOptions(screen.getByLabelText("File type"), "image");

    await waitFor(() => expect(location()).toBe("/?type=image"));
    await waitFor(() => expect(server.last("GET /files/").params.type).toBe("image"));
    expect(server.last("GET /files/").params.page).toBeUndefined();
  });

  it("a URL with filters (reload) shows the same view", async () => {
    const server = startDashboard("/?search=invoice&type=pdf&page=2");

    await screen.findByText("invoice_41.pdf");

    expect(screen.getByLabelText("Search files")).toHaveValue("invoice");
    expect(screen.getByLabelText("File type")).toHaveValue("pdf");
    expect(server.last("GET /files/").params).toEqual({ search: "invoice", type: "pdf", page: 2 });
    expect(screen.getByText("Showing 21–23 of 23")).toBeInTheDocument();
  });

  it("browser Back restores the previous search in the box and the list", async () => {
    startDashboard(["/?search=photo", "/?search=invoice"]);
    await screen.findByText("invoice_1.pdf");

    await userEvent.click(screen.getByRole("button", { name: "test-back", hidden: true }));

    await waitFor(() => expect(location()).toBe("/?search=photo"));
    expect(screen.getByLabelText("Search files")).toHaveValue("photo");
    expect(await screen.findByText("photo_2.png")).toBeInTheDocument();
  });
});

describe("pagination", () => {
  it("Prev/Next move between pages and update 'Showing' + the URL", async () => {
    const server = startDashboard();
    await screen.findByText("invoice_1.pdf");

    expect(screen.getByText("Showing 1–20 of 45")).toBeInTheDocument();
    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "‹ Prev" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Next ›" }));
    expect(await screen.findByText("Showing 21–40 of 45")).toBeInTheDocument();
    expect(location()).toBe("/?page=2");
    expect(server.last("GET /files/").params.page).toBe(2);

    await userEvent.click(screen.getByRole("button", { name: "Next ›" }));
    expect(await screen.findByText("Showing 41–45 of 45")).toBeInTheDocument();
    expect(screen.getByText("Page 3 of 3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next ›" })).toBeDisabled();
    expect(cards()).toHaveLength(5);

    await userEvent.click(screen.getByRole("button", { name: "‹ Prev" }));
    expect(await screen.findByText("Showing 21–40 of 45")).toBeInTheDocument();
  });

  it("Back after Next returns to page 1", async () => {
    startDashboard();
    await screen.findByText("invoice_1.pdf");
    await userEvent.click(screen.getByRole("button", { name: "Next ›" }));
    await screen.findByText("Showing 21–40 of 45");

    await userEvent.click(screen.getByRole("button", { name: "test-back", hidden: true }));

    expect(await screen.findByText("Showing 1–20 of 45")).toBeInTheDocument();
  });

  it("a page that no longer exists offers to go to page 1", async () => {
    startDashboard("/?page=9");

    await userEvent.click(await screen.findByRole("button", { name: "Go to page 1" }));

    expect(await screen.findByText("Showing 1–20 of 45")).toBeInTheDocument();
    expect(location()).toBe("/");
  });
});

describe("empty and error states", () => {
  it("says which search found nothing, with a way to clear it", async () => {
    startDashboard("/?search=zzz");

    expect(await screen.findByText('No files match "zzz".')).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));

    expect(await screen.findByText("invoice_1.pdf")).toBeInTheDocument();
    expect(screen.getByLabelText("Search files")).toHaveValue("");
  });

  it("an empty vault says so", async () => {
    startDashboard("/", { routes: { "GET /files/": EMPTY_PAGE } });

    expect(await screen.findByText("No files yet.")).toBeInTheDocument();
  });

  it("shows an error with Retry, and Retry loads the list", async () => {
    let fail = true;
    startDashboard("/", {
      routes: { "GET /files/": (config) => (fail ? { status: 500, data: { detail: "Server exploded" } } : filesEndpoint(config)) },
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load files. Server exploded");

    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("invoice_1.pdf")).toBeInTheDocument();
  });
});

describe("preview modal", () => {
  const blobResponse = (type) => ({ status: 200, data: new Blob(["bytes"], { type }) });

  it("PDF: spinner, then an iframe with a blob URL; closing revokes the URL", async () => {
    const preview = deferred();
    startDashboard("/", { routes: { "GET /files/1/preview/": preview.promise } });
    await userEvent.click(await screen.findByRole("button", { name: "Preview invoice_1.pdf" }));

    const dialog = screen.getByRole("dialog", { name: "invoice_1.pdf" });
    expect(within(dialog).getByText("Decrypting...")).toBeInTheDocument();

    await act(async () => preview.resolve(blobResponse("application/pdf")));

    const frame = within(dialog).getByTitle("invoice_1.pdf");
    expect(frame.tagName).toBe("IFRAME");
    const blobUrl = frame.getAttribute("src");
    expect(blobUrl).toMatch(/^blob:fake-/);
    // the blob is re-typed with the stored MIME type
    expect(URL.createObjectURL.mock.calls.at(-1)[0].type).toBe("application/pdf");

    await userEvent.click(within(dialog).getByRole("button", { name: "Close" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith(blobUrl);
  });

  it("image: shown in an <img>", async () => {
    startDashboard("/", { routes: { "GET /files/2/preview/": blobResponse("image/png") } });
    await userEvent.click(await screen.findByRole("button", { name: "Preview photo_2.png" }));

    const image = await screen.findByRole("img", { name: "photo_2.png" });
    expect(image.getAttribute("src")).toMatch(/^blob:fake-/);
  });

  it("decryption error: shows the backend's JSON message from the blob body", async () => {
    const body = new Blob(
      [JSON.stringify({ detail: "Could not decrypt file: it was modified or encrypted with a different key." })],
      { type: "application/json" },
    );
    startDashboard("/", { routes: { "GET /files/1/preview/": { status: 500, data: body } } });
    await userEvent.click(await screen.findByRole("button", { name: "Preview invoice_1.pdf" }));

    const dialog = screen.getByRole("dialog");
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Could not decrypt file: it was modified or encrypted with a different key.",
    );
    expect(within(dialog).queryByTitle("invoice_1.pdf")).not.toBeInTheDocument();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });

  it("Escape closes the modal", async () => {
    startDashboard("/", { routes: { "GET /files/1/preview/": blobResponse("application/pdf") } });
    await userEvent.click(await screen.findByRole("button", { name: "Preview invoice_1.pdf" }));
    await within(screen.getByRole("dialog")).findByTitle("invoice_1.pdf");

    await userEvent.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(URL.revokeObjectURL).toHaveBeenCalled();
  });

  it("closing while still loading cancels without creating a URL", async () => {
    const preview = deferred();
    startDashboard("/", { routes: { "GET /files/1/preview/": preview.promise } });
    await userEvent.click(await screen.findByRole("button", { name: "Preview invoice_1.pdf" }));

    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    await act(async () => preview.resolve(blobResponse("application/pdf")));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("download from a card", () => {
  it("uses the filename from Content-Disposition", async () => {
    startDashboard("/", {
      routes: {
        "GET /files/1/download/": {
          status: 200, data: new Blob(["%PDF-"]),
          headers: { "content-disposition": 'attachment; filename="invoice_1.pdf"' },
        },
      },
    });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function () {
      click.savedAs = this.download;
    });

    await userEvent.click(await screen.findByRole("button", { name: "Download invoice_1.pdf" }));

    await waitFor(() => expect(click.savedAs).toBe("invoice_1.pdf"));
    click.mockRestore();
  });

  it("shows the backend's error if the download fails", async () => {
    const body = new Blob([JSON.stringify({ detail: "The stored file is missing on the server." })]);
    startDashboard("/", { routes: { "GET /files/1/download/": { status: 500, data: body } } });

    await userEvent.click(await screen.findByRole("button", { name: "Download invoice_1.pdf" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Download failed: The stored file is missing on the server.",
    );
  });
});
