import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { describeError } from "../api/errors";
import { useAuth } from "../auth/useAuth";
import AuthCard from "../components/AuthCard";
import SubmitButton from "../components/SubmitButton";
import TextField from "../components/TextField";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [form, setForm] = useState({ username: "", password: "" });
  const [errors, setErrors] = useState({ message: null, fieldErrors: {} });
  const [sending, setSending] = useState(false);

  const onChange = (event) => setForm({ ...form, [event.target.name]: event.target.value });

  async function onSubmit(event) {
    event.preventDefault();
    setSending(true);
    setErrors({ message: null, fieldErrors: {} });
    try {
      await login(form.username, form.password);
      navigate(location.state?.from || "/", { replace: true }); // back to where they were going
    } catch (error) {
      setErrors(describeError(error));
      setSending(false);
    }
  }

  return (
    <AuthCard title="Sign in to your account" error={errors.message}>
      <form onSubmit={onSubmit} noValidate>
        <TextField label="Username" name="username" value={form.username} onChange={onChange}
          errors={errors.fieldErrors.username} autoComplete="username" required autoFocus />
        <TextField label="Password" name="password" type="password" value={form.password}
          onChange={onChange} errors={errors.fieldErrors.password} autoComplete="current-password" required />
        <SubmitButton sending={sending}>Log in</SubmitButton>
      </form>
      <p className="text-center mt-3 mb-0">
        No account? <Link to="/register">Register</Link>
      </p>
    </AuthCard>
  );
}
