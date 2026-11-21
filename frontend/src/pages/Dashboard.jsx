import { useAuth } from "../auth/useAuth";
import Navbar from "../components/Navbar";

// Placeholder for Phase 8. The file grid, search and preview arrive in Phase 9.
export default function Dashboard() {
  const { user } = useAuth();

  return (
    <>
      <Navbar />
      <main className="container py-4">
        <h2 className="h4">Welcome, {user.username}</h2>
        <p className="text-muted">
          You are logged in{user.is_staff ? " as an admin" : ""}. The file list comes next.
        </p>
      </main>
    </>
  );
}
