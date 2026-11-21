import { useState } from "react";
import { describeChangeError } from "../../api/errors";
import { renameFile, replaceFile } from "../../api/files";
import { useFileUpload } from "../../hooks/useFileUpload";
import { acceptFor } from "../../utils/fileCheck";
import Modal from "../Modal";
import TextField from "../TextField";
import FilePicker from "./FilePicker";
import UploadProgress from "./UploadProgress";

// Two tabs: Rename (PATCH) and Replace content (PUT replace/).
// onSaved(updatedFile, message) is called after either succeeds.
export default function EditModal({ file, onClose, onSaved }) {
  const [tab, setTab] = useState("rename");
  const [busy, setBusy] = useState(false);

  return (
    <Modal title={`Edit ${file.original_name}`} onClose={onClose} busy={busy}>
      <ul className="nav nav-tabs mb-3" role="tablist">
        {[["rename", "Rename"], ["replace", "Replace file"]].map(([key, label]) => (
          <li className="nav-item" key={key}>
            <button type="button" role="tab" aria-selected={tab === key} disabled={busy}
              className={`nav-link ${tab === key ? "active" : ""}`} onClick={() => setTab(key)}>
              {label}
            </button>
          </li>
        ))}
      </ul>
      {tab === "rename"
        ? <RenameForm file={file} onClose={onClose} onSaved={onSaved} setBusy={setBusy} />
        : <ReplaceForm file={file} onClose={onClose} onSaved={onSaved} setBusy={setBusy} />}
    </Modal>
  );
}

const extensionOf = (name) => (name.includes(".") ? name.slice(name.lastIndexOf(".")) : "");

function RenameForm({ file, onClose, onSaved, setBusy }) {
  const [name, setName] = useState(file.original_name);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState({ message: null, fieldErrors: {} });

  async function onSubmit(event) {
    event.preventDefault();
    setSending(true);
    setBusy(true);
    setError({ message: null, fieldErrors: {} });
    try {
      const saved = await renameFile(file.id, name);
      onSaved(saved, `Renamed to ${saved.original_name}`);
    } catch (err) {
      setError(describeChangeError(err));
      setSending(false);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate>
      {error.message && <div className="alert alert-danger" role="alert">{error.message}</div>}
      <TextField label="New name" name="original_name" value={name} maxLength={255} required
        onChange={(e) => setName(e.target.value)} errors={error.fieldErrors.original_name} disabled={sending} />
      <p className="form-text mt-n2">
        The extension stays <strong>{extensionOf(file.original_name)}</strong>: whatever you type after the
        last dot is replaced, because the content is still a {file.file_type === "pdf" ? "PDF" : "image"}.
      </p>
      <div className="d-flex justify-content-end gap-2">
        <button type="button" className="btn btn-secondary" onClick={onClose} disabled={sending}>Cancel</button>
        <button type="submit" className="btn btn-primary" disabled={sending || !name.trim()}>
          {sending && <span className="spinner-border spinner-border-sm me-1" aria-hidden="true" />}
          Save name
        </button>
      </div>
    </form>
  );
}

function ReplaceForm({ file, onClose, onSaved, setBusy }) {
  const upload = useFileUpload((chosen, onProgress) => replaceFile(file.id, chosen, onProgress), file.file_type);
  const kind = file.file_type === "pdf" ? "a PDF" : "an image (PNG or JPG)";

  async function onSubmit(event) {
    event.preventDefault();
    setBusy(true);
    const saved = await upload.submit();
    setBusy(false);
    if (saved) onSaved(saved, `Replaced the content of ${saved.original_name}`);
  }

  return (
    <form onSubmit={onSubmit}>
      <p className="text-muted small">
        Uploads new content under the same name. It must be {kind}, like the current file.
      </p>
      {upload.message && <div className="alert alert-danger" role="alert">{upload.message}</div>}
      <FilePicker file={upload.file} onSelect={upload.select} accept={acceptFor(file.file_type)}
        errors={upload.errors} disabled={upload.sending} />
      {upload.sending && <UploadProgress percent={upload.progress} />}
      <div className="d-flex justify-content-end gap-2">
        <button type="button" className="btn btn-secondary" onClick={onClose} disabled={upload.sending}>Cancel</button>
        <button type="submit" className="btn btn-primary"
          disabled={!upload.file || upload.errors.length > 0 || upload.sending}>
          {upload.sending && <span className="spinner-border spinner-border-sm me-1" aria-hidden="true" />}
          Replace
        </button>
      </div>
    </form>
  );
}
