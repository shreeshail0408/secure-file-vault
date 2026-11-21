import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { describeError } from "../api/errors";
import { useAuth } from "../auth/useAuth";
import AuthCard from "../components/AuthCard";
import SubmitButton from "../components/SubmitButton";
import TextField from "../components/TextField";

const EMPTY = { username: "", email: "", password: "", confirm_password: "" };

export default function Register() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState({ message: null, fieldErrors: {} });
  const [sending, setSending] = useState(false);

  const onChange = (event) => setForm({ ...form, [event.target.name]: event.target.value });

  async function onSubmit(event) {
    event.preventDefault();
    setSending(true);
    setErrors({ message: null, fieldErrors: {} });
    try {
      await api.post("/auth/register/", form);
      await login(form.username, form.password); // sign straight in after registering
      navigate("/", { replace: true });
    } catch (error) {
      setErrors(describeError(error));
      setSending(false);
    }
  }

  const fieldErrors = errors.fieldErrors;
  return (
    <AuthCard title="Create an account" error={errors.message}>
      <form onSubmit={onSubmit} noValidate>
        <TextField label="Username" name="username" value={form.username} onChange={onChange}
          errors={fieldErrors.username} autoComplete="username" required autoFocus />
        <TextField label="Email" name="email" type="email" value={form.email} onChange={onChange}
          errors={fieldErrors.email} autoComplete="email" required />
        <TextField label="Password" name="password" type="password" value={form.password}
          onChange={onChange} errors={fieldErrors.password} autoComplete="new-password" required />
        <TextField label="Confirm password" name="confirm_password" type="password"
          value={form.confirm_password} onChange={onChange} errors={fieldErrors.confirm_password}
          autoComplete="new-password" required />
        <SubmitButton sending={sending}>Register</SubmitButton>
      </form>
      <p className="text-center mt-3 mb-0">
        Already have an account? <Link to="/login">Log in</Link>
      </p>
    </AuthCard>
  );
}
