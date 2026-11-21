// Shared centered card layout for the Login and Register pages.
export default function AuthCard({ title, error, children }) {
  return (
    <div className="container d-flex justify-content-center align-items-center min-vh-100">
      <div className="card shadow-sm" style={{ width: "100%", maxWidth: 420 }}>
        <div className="card-body p-4">
          <h1 className="h4 mb-1 text-center">Secure File Vault</h1>
          <p className="text-muted text-center mb-4">{title}</p>
          {error && <div className="alert alert-danger" role="alert">{error}</div>}
          {children}
        </div>
      </div>
    </div>
  );
}
