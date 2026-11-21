import { afterEach, describe, expect, it, vi } from "vitest";
import { fakeServer } from "../test/fakeServer";
import { setTokens } from "./tokens";
import { describeBlobError, downloadFile, filenameFromDisposition } from "./files";

describe("filenameFromDisposition", () => {
  // Header values exactly as Django's content_disposition_header produces them
  // (see backend files/test_api.py ContentDispositionTests).
  it.each([
    ['attachment; filename="report.pdf"', "report.pdf"],
    ['inline; filename="report.pdf"', "report.pdf"],
    ['attachment; filename="my \\"best\\" report.pdf"', 'my "best" report.pdf'],
    ["attachment; filename*=utf-8''r%C3%A9sum%C3%A9.pdf", "résumé.pdf"],
    ["attachment; filename*=utf-8''evil%0D%0ASet-Cookie%3A%20x%3D1.pdf", "evil\r\nSet-Cookie: x=1.pdf"],
    ["attachment; filename*=UTF-8''photo%20one.jpg", "photo one.jpg"],
    ['attachment; filename="vault-export-2026-11-21.zip"', "vault-export-2026-11-21.zip"],
    ["attachment; filename=plain.pdf", "plain.pdf"],
  ])("%s → %s", (header, expected) => {
    expect(filenameFromDisposition(header)).toBe(expected);
  });

  it("prefers filename* over filename when both are present", () => {
    const header = "attachment; filename=\"resume.pdf\"; filename*=utf-8''r%C3%A9sum%C3%A9.pdf";
    expect(filenameFromDisposition(header)).toBe("résumé.pdf");
  });

  it("falls back to filename when filename* is badly encoded", () => {
    expect(filenameFromDisposition("attachment; filename=\"ok.pdf\"; filename*=utf-8''bad%E0%A4%A.pdf")).toBe("ok.pdf");
  });

  it("returns null without a filename", () => {
    expect(filenameFromDisposition(undefined)).toBeNull();
    expect(filenameFromDisposition("attachment")).toBeNull();
  });
});

describe("downloadFile", () => {
  afterEach(() => vi.restoreAllMocks());

  function captureSavedName() {
    const saved = {};
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function () {
      saved.name = this.download;
      saved.href = this.href;
    });
    return saved;
  }

  it("saves the blob under the server's filename", async () => {
    setTokens({ access: "a", refresh: "r" });
    fakeServer({
      "GET /files/7/download/": {
        status: 200, data: new Blob(["%PDF-"]),
        headers: { "content-disposition": "attachment; filename*=utf-8''r%C3%A9sum%C3%A9.pdf" },
      },
    });
    const saved = captureSavedName();

    await downloadFile("/files/7/download/", "fallback.pdf");

    expect(saved.name).toBe("résumé.pdf");
    expect(saved.href).toMatch(/^blob:fake-/);
  });

  it("uses the fallback name when the header is missing", async () => {
    fakeServer({ "GET /files/7/download/": { status: 200, data: new Blob(["x"]) } });
    const saved = captureSavedName();

    await downloadFile("/files/7/download/", "report.pdf");

    expect(saved.name).toBe("report.pdf");
  });
});

describe("describeBlobError", () => {
  it("reads the JSON detail out of a Blob error body", async () => {
    const body = new Blob([JSON.stringify({ detail: "Could not decrypt file: it was modified." })],
      { type: "application/json" });
    const error = { response: { status: 500, data: body } };

    expect(await describeBlobError(error)).toBe("Could not decrypt file: it was modified.");
  });

  it("falls back to a generic message for non-JSON bodies", async () => {
    const error = { response: { status: 502, data: new Blob(["<html>Bad gateway</html>"]) } };

    expect(await describeBlobError(error)).toBe("Something went wrong (error 502).");
  });
});
