// File API calls + helpers for blob downloads.
import { api } from "./client";
import { describeError } from "./errors";

// Must match REST_FRAMEWORK["PAGE_SIZE"] in backend/config/settings.py.
export const PAGE_SIZE = 20;

export function listFiles({ search, type, page }, { signal } = {}) {
  return api
    .get("/files/", {
      // undefined values are left out of the query string
      params: { search: search.trim() || undefined, type: type || undefined, page: page > 1 ? page : undefined },
      signal,
    })
    .then((response) => response.data); // { count, next, previous, results }
}

// --- Changing files (each resolves to the updated file object from the API) ---

// Upload / replace send multipart form data with the file in field "file".
// onProgress(percent) is called as the browser sends the bytes.
function sendFile(method, url, file, onProgress) {
  const form = new FormData();
  form.append("file", file);
  return api
    .request({
      method,
      url,
      data: form,
      onUploadProgress: (event) => event.total && onProgress?.(Math.round((100 * event.loaded) / event.total)),
    })
    .then((response) => response.data);
}

export const uploadFile = (file, onProgress) => sendFile("post", "/files/", file, onProgress);

export const replaceFile = (id, file, onProgress) => sendFile("put", `/files/${id}/replace/`, file, onProgress);

export const renameFile = (id, name) =>
  api.patch(`/files/${id}/`, { original_name: name }).then((response) => response.data);

export const deleteFile = (id) => api.delete(`/files/${id}/`);

// GET a file as a Blob (preview, download, export). Goes through `api`, so an
// expired access token is refreshed automatically.
export function fetchBlob(url, { signal } = {}) {
  return api.get(url, { responseType: "blob", signal });
}

// Download: save the blob under the server's filename (Content-Disposition), or `fallbackName`.
export async function downloadFile(url, fallbackName) {
  const response = await fetchBlob(url);
  const name = filenameFromDisposition(response.headers["content-disposition"]) || fallbackName;
  saveBlob(response.data, name);
  return name;
}

// Parses both forms Django sends (see backend preview/download views):
//   attachment; filename="report.pdf"            (quotes and \ escaped with \)
//   attachment; filename*=utf-8''r%C3%A9sum%C3%A9.pdf   (RFC 5987, for non-ASCII etc.)
// filename* wins when both are present. Returns null if there is no filename.
export function filenameFromDisposition(header) {
  if (!header) return null;

  const encoded = /filename\*\s*=\s*([\w-]+)''([^;]+)/i.exec(header);
  if (encoded) {
    try {
      return decodeURIComponent(encoded[2].trim());
    } catch {
      // malformed %-encoding: fall back to the plain filename below
    }
  }

  const quoted = /filename\s*=\s*"((?:\\.|[^"\\])*)"/i.exec(header);
  if (quoted) return quoted[1].replace(/\\(.)/g, "$1"); // un-escape \" and \\

  const bare = /filename\s*=\s*([^;]+)/i.exec(header);
  return bare ? bare[1].trim() : null;
}

// Make the browser save a Blob: temporary object URL + <a download>.
export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Give the browser a moment to start the download before freeing the memory.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// With responseType "blob", even JSON error bodies (e.g. {"detail": "Could not
// decrypt file..."}) arrive as a Blob, so read and parse it before describing it.
export async function describeBlobError(error) {
  const data = error.response?.data;
  if (data instanceof Blob) {
    let parsed = null;
    try {
      parsed = JSON.parse(await data.text());
    } catch {
      // not JSON: describeError falls back to a generic message
    }
    error = { ...error, response: { ...error.response, data: parsed } };
  }
  return describeError(error).message;
}
