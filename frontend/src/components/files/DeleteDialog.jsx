import { useState } from "react";
import { describeChangeError } from "../../api/errors";
import { deleteFile } from "../../api/files";
import Modal from "../Modal";

export default function DeleteDialog({ file, onClose, onDeleted }) {
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);

  async function confirm() {
    setSending(true);
    setError(null);
    try {
      await deleteFile(file.id);
      onDeleted(file);
    } catch (err) {
      setError(describeChangeError(err).message);
      setSending(false);
    }
  }

  return (
    <Modal title="Delete file?" onClose={onClose} busy={sending}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={sending}>Cancel</button>
          <button type="button" className="btn btn-danger" onClick={confirm} disabled={sending}>
            {sending && <span className="spinner-border spinner-border-sm me-1" aria-hidden="true" />}
            Delete
          </button>
        </>
      }>
      {error && <div className="alert alert-danger" role="alert">{error}</div>}
      <p className="mb-0">
        Delete <strong>{file.original_name}</strong>? The encrypted file is removed from the server.
        This cannot be undone.
      </p>
    </Modal>
  );
}
