// Disabled with a small spinner while the form is being sent (no double submits).
export default function SubmitButton({ sending, children }) {
  return (
    <button type="submit" className="btn btn-primary w-100" disabled={sending}>
      {sending && <span className="spinner-border spinner-border-sm me-2" aria-hidden="true" />}
      {sending ? "Please wait..." : children}
    </button>
  );
}
