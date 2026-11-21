import { useState } from "react";

// A button for async actions: disabled with a spinner until onClick's promise settles.
export default function BusyButton({ onClick, className = "btn btn-outline-secondary btn-sm", children, ...rest }) {
  const [busy, setBusy] = useState(false);

  async function handleClick() {
    setBusy(true);
    try {
      await onClick();
    } finally {
      setBusy(false);
    }
  }

  return (
    <button type="button" className={className} onClick={handleClick} disabled={busy} {...rest}>
      {busy && <span className="spinner-border spinner-border-sm me-1" aria-hidden="true" />}
      {children}
    </button>
  );
}
