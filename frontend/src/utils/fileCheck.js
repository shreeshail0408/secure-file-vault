// Quick checks in the browser BEFORE uploading, for fast feedback.
// The backend still decides (it checks the real content / magic bytes),
// so these only need to catch the obvious mistakes.

export const MAX_UPLOAD_MB = 10; // must match MAX_UPLOAD_SIZE in backend/config/settings.py

const EXTENSIONS = { pdf: [".pdf"], image: [".png", ".jpg", ".jpeg"] };
const MIME_TYPES = { pdf: ["application/pdf"], image: ["image/png", "image/jpeg"] };

// For <input accept="...">: what the file dialog offers.
export function acceptFor(fileType) {
  const types = fileType ? [fileType] : ["pdf", "image"];
  return types.flatMap((t) => [...EXTENSIONS[t], ...MIME_TYPES[t]]).join(",");
}

// Returns an error message, or null if the file looks fine.
// fileType: "pdf" / "image" when replacing (must stay the same type), or null for any.
export function checkFile(file, fileType = null) {
  const types = fileType ? [fileType] : ["pdf", "image"];
  const name = file.name.toLowerCase();
  const extensionOk = types.some((t) => EXTENSIONS[t].some((ext) => name.endsWith(ext)));
  // Browsers sometimes leave file.type empty; then the extension decides.
  const mimeOk = !file.type || types.some((t) => MIME_TYPES[t].includes(file.type));

  if (!extensionOk || !mimeOk) {
    if (fileType === "pdf") return "The new file must be a PDF, like the current one.";
    if (fileType === "image") return "The new file must be an image (PNG or JPG), like the current one.";
    return "Only PDF, PNG and JPG files are allowed.";
  }
  if (file.size === 0) return "The file is empty.";
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) return `The file is too large (max ${MAX_UPLOAD_MB} MB).`;
  return null;
}
