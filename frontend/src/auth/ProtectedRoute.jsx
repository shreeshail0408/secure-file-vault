import { Navigate, useLocation } from "react-router-dom";
import Spinner from "../components/Spinner";
import { useAuth } from "./useAuth";

// Only for logged-in users. While we're still checking the saved token, show a
// spinner (not the login page), then either the page or a redirect to /login.
export default function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <Spinner />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return children;
}
