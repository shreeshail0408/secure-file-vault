import { useEffect, useState } from "react";
import { describeBlobError, fetchBlob } from "../../api/files";
import BusyButton from "../BusyButton";

// Fetches the decrypted file as a Blob (an <iframe src> can't send our JWT header),
// shows it from a temporary blob: URL, and frees that URL when closed.
export default function PreviewModal({ file, onClose, onDownload }) {
  // Like useFileList: `loading` = "no result for THIS file yet".
  const [result, setResult] = useState({ fileId: null, url: null, error: null });
  const loading = result.fileId !== file.id;

  useEffect(() => {
    const controller = new AbortController();
    let objectUrl = null;

    fetchBlob(`/files/${file.id}/preview/`, { signal: controller.signal })
      .then((response) => {
        // Re-wrap with the type we stored at upload (PDF/PNG/JPEG only), so the
        // browser never treats the content as anything else (e.g. HTML).
        objectUrl = URL.createObjectURL(new Blob([response.data], { type: file.mime_type }));
        setResult({ fileId: file.id, url: objectUrl, error: null });
      })
      .catch(async (error) => {
        if (controller.signal.aborted) return;
        setResult({ fileId: file.id, url: null, error: await describeBlobError(error) });
      });

    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl); // free the decrypted copy in memory
    };
  }, [file.id, file.mime_type]);

  // Close on Escape.
  useEffect(() => {
    const onKey = (event) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <>
      <div className="modal d-block" role="dialog" aria-modal="true" aria-labelledby="preview-title"
        onClick={(event) => event.target === event.currentTarget && onClose()}>
        <div className="modal-dialog modal-xl modal-dialog-centered modal-dialog-scrollable">
          <div className="modal-content">
            <div className="modal-header">
              <h2 className="modal-title h5 text-truncate" id="preview-title">{file.original_name}</h2>
              <button type="button" className="btn-close" aria-label="Close preview" onClick={onClose} />
            </div>
            <div className="modal-body text-center" style={{ minHeight: 300 }}>
              {loading && (
                <div className="spinner-border text-primary my-5" role="status">
                  <span className="visually-hidden">Decrypting...</span>
                </div>
              )}
              {!loading && result.error && <div className="alert alert-danger text-start" role="alert">{result.error}</div>}
              {!loading && result.url && file.file_type === "pdf" && (
                <iframe src={result.url} title={file.original_name} className="w-100 border-0" style={{ height: "75vh" }} />
              )}
              {!loading && result.url && file.file_type === "image" && (
                <img src={result.url} alt={file.original_name} className="img-fluid" style={{ maxHeight: "75vh" }} />
              )}
            </div>
            <div className="modal-footer">
              <BusyButton className="btn btn-outline-primary" onClick={() => onDownload(file)}>
                <i className="bi bi-download me-1" aria-hidden="true" />Download
              </BusyButton>
              <button type="button" className="btn btn-secondary" onClick={onClose}>Close</button>
            </div>
          </div>
        </div>
      </div>
      <div className="modal-backdrop show" />
    </>
  );
}
