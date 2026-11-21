import { useState } from "react";
import { describeChangeError } from "../api/errors";
import { checkFile } from "../utils/fileCheck";

// Shared state for "pick a file and send it" (Upload and Replace):
// the chosen file, the browser pre-check, progress and the backend's errors.
//
// send(file, onProgress) must return a promise (uploadFile / replaceFile).
// fileType: null for any type, or "pdf" / "image" when replacing.
export function useFileUpload(send, fileType = null) {
  const [file, setFile] = useState(null);
  const [errors, setErrors] = useState([]); // messages shown under the picker
  const [progress, setProgress] = useState(null); // null = not sending
  const [message, setMessage] = useState(null); // general error (alert)

  function select(chosen) {
    setFile(chosen);
    setMessage(null);
    const problem = checkFile(chosen, fileType);
    setErrors(problem ? [problem] : []);
  }

  // Resolves to the saved file object, or null if it failed (errors are then shown).
  async function submit() {
    if (!file || errors.length) return null;
    setMessage(null);
    setProgress(0);
    try {
      return await send(file, setProgress);
    } catch (error) {
      const { message: text, fieldErrors } = describeChangeError(error);
      // The backend puts upload problems under "file" (wrong type, too large, ...).
      setErrors(fieldErrors.file || []);
      setMessage(text || (fieldErrors.file ? null : "The upload failed."));
      return null;
    } finally {
      setProgress(null);
    }
  }

  return { file, select, errors, message, progress, sending: progress !== null, submit };
}
