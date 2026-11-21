import { useEffect } from "react";

// Bootstrap-styled modal without Bootstrap's JavaScript: React decides when it's shown.
// Closes on Escape, the × button, or a click on the dark background,
// unless `busy` is set (e.g. while an upload is running).
export default function Modal({ title, onClose, footer, children, size = "", busy = false }) {
  const close = () => !busy && onClose();

  useEffect(() => {
    const onKey = (event) => event.key === "Escape" && !busy && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, busy]);

  return (
    <>
      <div className="modal d-block" role="dialog" aria-modal="true" aria-labelledby="modal-title"
        onClick={(event) => event.target === event.currentTarget && close()}>
        <div className={`modal-dialog modal-dialog-centered modal-dialog-scrollable ${size}`}>
          <div className="modal-content">
            <div className="modal-header">
              <h2 className="modal-title h5 text-truncate" id="modal-title">{title}</h2>
              <button type="button" className="btn-close" aria-label="Close dialog" onClick={close} disabled={busy} />
            </div>
            <div className="modal-body">{children}</div>
            {footer && <div className="modal-footer">{footer}</div>}
          </div>
        </div>
      </div>
      <div className="modal-backdrop show" />
    </>
  );
}
