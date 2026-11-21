import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";

export default function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  function onLogout() {
    logout(); // clears both tokens
    navigate("/login", { replace: true });
  }

  return (
    <nav className="navbar navbar-dark bg-dark">
      <div className="container">
        <span className="navbar-brand">Secure File Vault</span>
        <div className="d-flex align-items-center gap-3 text-light">
          <span>
            {user.username}
            {user.is_staff && <span className="badge bg-warning text-dark ms-2">Admin</span>}
          </span>
          <button type="button" className="btn btn-outline-light btn-sm" onClick={onLogout}>
            Log out
          </button>
        </div>
      </div>
    </nav>
  );
}
