import { Navigate } from "react-router-dom";
import Spinner from "../components/Spinner";
import { useAuth } from "./useAuth";

// Login and Register: if you're already logged in, go to the dashboard instead.
export default function PublicOnlyRoute({ children }) {
  const { user, loading } = useAuth();

  if (loading) return <Spinner />;
  if (user) return <Navigate to="/" replace />;
  return children;
}
