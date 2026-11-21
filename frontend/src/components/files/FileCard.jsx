import { formatDate, formatSize } from "../../utils/format";
import BusyButton from "../BusyButton";

// One file. A type icon instead of a thumbnail: thumbnails would mean
// decrypting every image on the page on the server.
const LOOK = {
  pdf: { icon: "bi-file-earmark-pdf", color: "text-danger", label: "PDF" },
  image: { icon: "bi-file-earmark-image", color: "text-primary", label: "Image" },
};

export default function FileCard({ file, onPreview, onDownload }) {
  const look = LOOK[file.file_type] || LOOK.pdf;

  return (
    <div className="card h-100 shadow-sm" data-testid="file-card">
      <div className="card-body">
        <div className="d-flex align-items-start gap-3">
          <i className={`bi ${look.icon} ${look.color} fs-1`} aria-hidden="true" />
          <div className="flex-grow-1" style={{ minWidth: 0 }}>
            <h3 className="h6 card-title text-truncate mb-1" title={file.original_name}>
              {file.original_name}
            </h3>
            <span className="badge text-bg-light border">{look.label}</span>
          </div>
        </div>
        <dl className="small text-muted mt-3 mb-0">
          <div><dt className="d-inline">Size: </dt><dd className="d-inline">{formatSize(file.size)}</dd></div>
          <div><dt className="d-inline">Date: </dt><dd className="d-inline">{formatDate(file.created_at)}</dd></div>
          <div><dt className="d-inline">By: </dt><dd className="d-inline">{file.uploaded_by || "deleted user"}</dd></div>
        </dl>
      </div>
      <div className="card-footer bg-white d-flex flex-wrap gap-2">
        <button type="button" className="btn btn-primary btn-sm" onClick={() => onPreview(file)}
          aria-label={`Preview ${file.original_name}`}>
          <i className="bi bi-eye me-1" aria-hidden="true" />Preview
        </button>
        <BusyButton onClick={() => onDownload(file)} aria-label={`Download ${file.original_name}`}>
          <i className="bi bi-download me-1" aria-hidden="true" />Download
        </BusyButton>
        {/* Hiding these is only UX; the API still returns 403 for other people's files. */}
        {file.can_edit && (
          <>
            <button type="button" className="btn btn-outline-secondary btn-sm" disabled title="Coming in Phase 10">
              Edit
            </button>
            <button type="button" className="btn btn-outline-danger btn-sm" disabled title="Coming in Phase 10">
              Delete
            </button>
          </>
        )}
      </div>
    </div>
  );
}
