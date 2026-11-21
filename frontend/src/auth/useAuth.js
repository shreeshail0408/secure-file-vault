import { createContext, useContext } from "react";

// The logged-in user and auth actions, provided by <AuthProvider> (AuthContext.jsx):
//   const { user, loading, login, logout } = useAuth();
// user is { id, username, email, is_staff } or null.
export const AuthContext = createContext(null);

export function useAuth() {
  return useContext(AuthContext);
}
