import { uploadFile } from "../../api/files";
import { useFileUpload } from "../../hooks/useFileUpload";
import { acceptFor, MAX_UPLOAD_MB } from "../../utils/fileCheck";
import Modal from "../Modal";
import FilePicker from "./FilePicker";
import UploadProgress from "./UploadProgress";

export default function UploadModal({ onClose, onUploaded }) {
  const upload = useFileUpload(uploadFile);

  async function onSubmit(event) {
    event.preventDefault();
    const saved = await upload.submit();
    if (saved) onUploaded(saved);
  }

  return (
    <Modal title="Upload a file" onClose={onClose} busy={upload.sending}>
      <form onSubmit={onSubmit}>
        <p className="text-muted small">PDF, PNG or JPG, up to {MAX_UPLOAD_MB} MB. It is encrypted on the server before it is stored.</p>
        {upload.message && <div className="alert alert-danger" role="alert">{upload.message}</div>}
        <FilePicker file={upload.file} onSelect={upload.select} accept={acceptFor(null)}
          errors={upload.errors} disabled={upload.sending} />
        {upload.sending && <UploadProgress percent={upload.progress} />}
        <div className="d-flex justify-content-end gap-2">
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={upload.sending}>Cancel</button>
          <button type="submit" className="btn btn-primary"
            disabled={!upload.file || upload.errors.length > 0 || upload.sending}>
            {upload.sending && <span className="spinner-border spinner-border-sm me-1" aria-hidden="true" />}
            Upload
          </button>
        </div>
      </form>
    </Modal>
  );
}
