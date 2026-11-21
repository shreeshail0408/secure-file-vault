import { useEffect } from "react";

// A small success message in the corner that disappears after a few seconds.
export default function Toast({ message, onDismiss, delay = 4000 }) {
  useEffect(() => {
    const timer = setTimeout(onDismiss, delay);
    return () => clearTimeout(timer);
  }, [message, onDismiss, delay]);

  return (
    <div className="toast-container position-fixed bottom-0 end-0 p-3">
      <div className="toast show text-bg-success border-0" role="status" aria-live="polite">
        <div className="d-flex">
          <div className="toast-body">
            <i className="bi bi-check-circle me-2" aria-hidden="true" />{message}
          </div>
          <button type="button" className="btn-close btn-close-white me-2 m-auto"
            aria-label="Dismiss" onClick={onDismiss} />
        </div>
      </div>
    </div>
  );
}
