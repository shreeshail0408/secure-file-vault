import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { deferred } from "../test/fakeServer";
import { makeFiles, startDashboard } from "../test/fileFixtures";
import { checkFile } from "../utils/fileCheck";

const location = () => screen.getByTestId("location").textContent;
const dialog = () => screen.getByRole("dialog");
const pdf = (name = "new.pdf", size = 1000) => fileOfSize(name, "application/pdf", size);
const png = (name = "new.png", size = 1000) => fileOfSize(name, "image/png", size);

// A File that claims a size without allocating it (for the 10 MB check).
function fileOfSize(name, type, size) {
  const file = new File(["x"], name, { type });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

const saved = (overrides) => ({ ...makeFiles(1)[0], ...overrides });

async function openUpload() {
  await userEvent.click(await screen.findByRole("button", { name: "Upload" }));
  return within(dialog());
}

describe("upload", () => {
  it("shows progress, then closes, shows a toast and reloads page 1", async () => {
    const files = makeFiles(45);
    const response = deferred();
    let sentFile = null;
    const server = startDashboard("/?page=2", {
      files,
      routes: {
        "POST /files/": (config) => {
          sentFile = config.data.get("file");
          config.onUploadProgress({ loaded: 50, total: 100 }); // browser has sent half
          return response.promise;
        },
      },
    });
    await screen.findByText("Showing 21–40 of 45");

    const modal = await openUpload();
    await userEvent.upload(modal.getByLabelText("Choose file"), pdf("contract.pdf"));
    expect(modal.getByText("contract.pdf")).toBeInTheDocument();
    await userEvent.click(modal.getByRole("button", { name: "Upload" }));

    const bar = await modal.findByRole("progressbar", { name: "Upload progress" });
    expect(bar).toHaveAttribute("aria-valuenow", "50");
    expect(bar).toHaveTextContent("50%");
    expect(modal.getByRole("button", { name: "Cancel" })).toBeDisabled(); // can't close mid-upload
    expect(sentFile.name).toBe("contract.pdf");

    files.unshift(saved({ id: 99, original_name: "contract.pdf" })); // newest first, like the API
    await act(async () => response.resolve({ status: 201, data: files[0] }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(await screen.findByText("Uploaded contract.pdf")).toBeInTheDocument();
    expect(location()).toBe("/");
    expect(await screen.findByText("Showing 1–20 of 46")).toBeInTheDocument();
    expect(server.last("GET /files/").params.page).toBeUndefined();
  });

  it("drag-and-drop selects the file", async () => {
    startDashboard();
    const modal = await openUpload();

    fireEvent.drop(modal.getByTestId("drop-zone"), { dataTransfer: { files: [png("dropped.png")] } });

    expect(modal.getByText("dropped.png")).toBeInTheDocument();
    expect(modal.getByRole("button", { name: "Upload" })).toBeEnabled();
  });

  it("rejects too-large and wrong-type files in the browser, without a request", async () => {
    const server = startDashboard();
    const modal = await openUpload();

    fireEvent.drop(modal.getByTestId("drop-zone"), { dataTransfer: { files: [pdf("big.pdf", 10 * 1024 * 1024 + 1)] } });
    expect(modal.getByRole("alert")).toHaveTextContent("The file is too large (max 10 MB).");
    expect(modal.getByRole("button", { name: "Upload" })).toBeDisabled();

    fireEvent.drop(modal.getByTestId("drop-zone"), { dataTransfer: { files: [new File(["MZ"], "tool.exe")] } });
    expect(modal.getByRole("alert")).toHaveTextContent("Only PDF, PNG and JPG files are allowed.");
    expect(modal.getByRole("button", { name: "Upload" })).toBeDisabled();

    expect(server.count("POST /files/")).toBe(0);
  });

  it("shows the backend's 400 error for the file under the picker", async () => {
    startDashboard("/", {
      routes: { "POST /files/": { status: 400, data: { file: ["The content is not a valid PDF, PNG or JPG file."] } } },
    });
    const modal = await openUpload();
    await userEvent.upload(modal.getByLabelText("Choose file"), pdf("fake.pdf"));

    await userEvent.click(modal.getByRole("button", { name: "Upload" }));

    expect(await modal.findByRole("alert")).toHaveTextContent("The content is not a valid PDF, PNG or JPG file.");
    expect(dialog()).toBeInTheDocument(); // stays open so the user can pick another file
  });
});

describe("checkFile (browser pre-check)", () => {
  it.each([
    [pdf("a.pdf"), null, null],
    [png("a.PNG"), null, null],
    [fileOfSize("a.jpeg", "image/jpeg", 10), null, null],
    [fileOfSize("a.pdf", "", 10), null, null], // browser gave no MIME type: extension decides
    [pdf("a.pdf", 0), null, "The file is empty."],
    [fileOfSize("a.pdf", "text/html", 10), null, "Only PDF, PNG and JPG files are allowed."],
    [png("a.png"), "pdf", "The new file must be a PDF, like the current one."],
    [pdf("a.pdf"), "image", "The new file must be an image (PNG or JPG), like the current one."],
    [fileOfSize("a.jpg", "image/jpeg", 10), "image", null], // PNG → JPG replace is allowed
  ])("%#", (file, fileType, expected) => {
    expect(checkFile(file, fileType)).toBe(expected);
  });
});

describe("rename", () => {
  async function openEdit(name = "invoice_1.pdf") {
    await userEvent.click(await screen.findByRole("button", { name: `Edit ${name}` }));
    return within(dialog());
  }

  it("is prefilled, explains the extension, saves and reloads the list", async () => {
    const files = makeFiles(45);
    let sent = null;
    const server = startDashboard("/", {
      files,
      routes: {
        "PATCH /files/1/": (config) => {
          sent = JSON.parse(config.data);
          files[0] = { ...files[0], original_name: "january.pdf" };
          return { status: 200, data: files[0] };
        },
      },
    });
    const modal = await openEdit();
    const input = modal.getByLabelText("New name");
    expect(input).toHaveValue("invoice_1.pdf");
    expect(modal.getByText(/The extension stays/)).toHaveTextContent("The extension stays .pdf");

    await userEvent.clear(input);
    await userEvent.type(input, "january.exe");
    await userEvent.click(modal.getByRole("button", { name: "Save name" }));

    expect(sent).toEqual({ original_name: "january.exe" }); // the backend forces .pdf
    expect(await screen.findByText("Renamed to january.pdf")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "january.pdf" })).toBeInTheDocument();
    expect(server.count("GET /files/")).toBe(2);
  });

  it("shows 400 field errors under the input", async () => {
    startDashboard("/", {
      routes: { "PATCH /files/1/": { status: 400, data: { original_name: ["The name cannot be empty."] } } },
    });
    const modal = await openEdit();
    await userEvent.clear(modal.getByLabelText("New name"));
    await userEvent.type(modal.getByLabelText("New name"), ".pdf");

    await userEvent.click(modal.getByRole("button", { name: "Save name" }));

    const input = modal.getByLabelText("New name");
    await waitFor(() => expect(input).toHaveClass("is-invalid"));
    expect(input).toHaveAccessibleDescription("The name cannot be empty.");
    expect(dialog()).toBeInTheDocument();
  });

  it("403 → 'you can't modify this file'", async () => {
    startDashboard("/", {
      routes: { "PATCH /files/1/": { status: 403, data: { detail: "You do not have permission to perform this action." } } },
    });
    const modal = await openEdit();

    await userEvent.click(modal.getByRole("button", { name: "Save name" }));

    expect(await modal.findByRole("alert")).toHaveTextContent("You can't modify this file: only its uploader or an admin can.");
  });
});

describe("replace", () => {
  async function openReplace() {
    await userEvent.click(await screen.findByRole("button", { name: "Edit invoice_1.pdf" }));
    const modal = within(dialog());
    await userEvent.click(modal.getByRole("tab", { name: "Replace file" }));
    return modal;
  }

  it("explains the same-type rule and rejects another type in the browser", async () => {
    const server = startDashboard();
    const modal = await openReplace();

    expect(modal.getByText(/It must be a PDF, like the current file/)).toBeInTheDocument();
    expect(modal.getByLabelText("Choose file")).toHaveAttribute("accept", ".pdf,application/pdf");

    fireEvent.drop(modal.getByTestId("drop-zone"), { dataTransfer: { files: [png("photo.png")] } });

    expect(modal.getByRole("alert")).toHaveTextContent("The new file must be a PDF, like the current one.");
    expect(modal.getByRole("button", { name: "Replace" })).toBeDisabled();
    expect(server.count("PUT /files/1/replace/")).toBe(0);
  });

  it("sends the new file with progress, then shows a toast", async () => {
    const response = deferred();
    startDashboard("/", {
      routes: {
        "PUT /files/1/replace/": (config) => {
          config.onUploadProgress({ loaded: 30, total: 40 });
          return response.promise;
        },
      },
    });
    const modal = await openReplace();
    await userEvent.upload(modal.getByLabelText("Choose file"), pdf("v2.pdf"));
    await userEvent.click(modal.getByRole("button", { name: "Replace" }));

    expect(await modal.findByRole("progressbar")).toHaveAttribute("aria-valuenow", "75");

    await act(async () => response.resolve({ status: 200, data: saved({ id: 1 }) }));

    expect(await screen.findByText("Replaced the content of invoice_1.pdf")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("403 and backend 400 errors are shown", async () => {
    let status = 403;
    startDashboard("/", {
      routes: {
        "PUT /files/1/replace/": () => (status === 403
          ? { status: 403, data: { detail: "You do not have permission to perform this action." } }
          : { status: 400, data: { file: ["The new file must be the same type as the old one (pdf)."] } }),
      },
    });
    const modal = await openReplace();
    await userEvent.upload(modal.getByLabelText("Choose file"), pdf("v2.pdf"));

    await userEvent.click(modal.getByRole("button", { name: "Replace" }));
    expect(await modal.findByRole("alert")).toHaveTextContent("You can't modify this file");

    status = 400;
    await userEvent.click(modal.getByRole("button", { name: "Replace" }));
    expect(await modal.findByText("The new file must be the same type as the old one (pdf).")).toBeInTheDocument();
  });
});

describe("delete", () => {
  async function openDelete(name) {
    await userEvent.click(await screen.findByRole("button", { name: `Delete ${name}` }));
    return within(dialog());
  }

  function deleteRoute(files, id) {
    return () => {
      files.splice(files.findIndex((f) => f.id === id), 1);
      return { status: 204, data: "" };
    };
  }

  it("asks first (naming the file); Cancel deletes nothing", async () => {
    const server = startDashboard();
    const modal = await openDelete("invoice_1.pdf");

    expect(modal.getByText("invoice_1.pdf", { selector: "strong" })).toBeInTheDocument();
    await userEvent.click(modal.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(server.calls.filter((c) => c.key.startsWith("DELETE"))).toEqual([]);
  });

  it("deletes, shows a toast and reloads the list", async () => {
    const files = makeFiles(45);
    startDashboard("/", { files, routes: { "DELETE /files/1/": deleteRoute(files, 1) } });
    const modal = await openDelete("invoice_1.pdf");

    await userEvent.click(modal.getByRole("button", { name: "Delete" }));

    expect(await screen.findByText("Deleted invoice_1.pdf")).toBeInTheDocument();
    expect(await screen.findByText("Showing 1–20 of 44")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "invoice_1.pdf" })).not.toBeInTheDocument();
  });

  it("deleting the last file on a page goes to the previous page", async () => {
    const files = makeFiles(41); // page 3 holds only invoice_41.pdf
    startDashboard("/?page=3", { files, routes: { "DELETE /files/41/": deleteRoute(files, 41) } });
    expect(await screen.findByText("Showing 41–41 of 41")).toBeInTheDocument();

    const modal = await openDelete("invoice_41.pdf");
    await userEvent.click(modal.getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(location()).toBe("/?page=2"));
    expect(await screen.findByText("Showing 21–40 of 40")).toBeInTheDocument();
    expect(screen.queryByText(/doesn't exist/)).not.toBeInTheDocument();
  });

  it("403 → clear message, the dialog stays open and the file stays", async () => {
    startDashboard("/", { routes: { "DELETE /files/1/": { status: 403, data: { detail: "Forbidden" } } } });
    const modal = await openDelete("invoice_1.pdf");

    await userEvent.click(modal.getByRole("button", { name: "Delete" }));

    expect(await modal.findByRole("alert")).toHaveTextContent("You can't modify this file: only its uploader or an admin can.");
    expect(screen.getByRole("heading", { name: "invoice_1.pdf" })).toBeInTheDocument();
  });
});

describe("dashboard", () => {
  it("no leftover placeholder text", async () => {
    startDashboard();
    await screen.findByText("invoice_1.pdf");
    expect(screen.queryByText(/comes next/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Phase 10/)).not.toBeInTheDocument();
  });
});
