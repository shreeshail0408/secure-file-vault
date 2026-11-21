// Fake files + a fake GET /files/ that behaves like the real API, shared by the dashboard tests.
import { setTokens } from "../api/tokens";
import { ALICE, fakeServer, renderApp } from "./fakeServer";

// n files; odd ids are Alice's PDFs (can_edit), even ids are Bob's PNGs.
export function makeFiles(n = 45) {
  return Array.from({ length: n }, (_, i) => ({
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
}

// Search, type filter, pages of 20, 404 for a page past the end. Reads `files`
// on every call, so tests can add/remove entries and the next load sees it.
export function listEndpoint(files) {
  return (config) => {
    const { search = "", type = "", page = 1 } = config.params || {};
    const matches = files.filter(
      (f) => f.original_name.toLowerCase().includes(search.toLowerCase()) && (!type || f.file_type === type),
    );
    const results = matches.slice((page - 1) * 20, page * 20);
    if (page > 1 && results.length === 0) return { status: 404, data: { detail: "Invalid page." } };
    return { status: 200, data: { count: matches.length, next: null, previous: null, results } };
  };
}

export function startDashboard(path = "/", { user = ALICE, routes = {}, files = makeFiles() } = {}) {
  setTokens({ access: "a", refresh: "r" });
  const server = fakeServer({ "GET /auth/me/": { status: 200, data: user }, "GET /files/": listEndpoint(files), ...routes });
  renderApp(path);
  return server;
}
