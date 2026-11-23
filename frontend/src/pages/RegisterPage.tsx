import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { isApiError } from "../api/errors";
import { InlineNotice } from "../components/feedback/InlineNotice";
import { Button } from "../components/ui/Button";
import { TextField } from "../components/ui/TextField";
import { useAuth } from "../features/auth/AuthProvider";
import { safeRedirect } from "../features/auth/ProtectedRoute";
import {
  hasErrors,
  validateRegistration,
  type AuthFieldErrors,
} from "../features/auth/validation";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

export default function RegisterPage() {
  useDocumentTitle("Create account");
  const { status, signIn } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const redirect = safeRedirect(searchParams.get("redirect"));

  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [errors, setErrors] = useState<AuthFieldErrors>({});

  const mutation = useMutation({
    mutationFn: async () => {
      const trimmedEmail = email.trim();
      await api.register({
        username: username.trim(),
        password,
        ...(trimmedEmail ? { email: trimmedEmail } : {}),
      });
      return api.login(username.trim(), password);
    },
    onSuccess: (response) => {
      signIn(response);
      navigate(redirect, { replace: true });
    },
  });

  if (status === "authenticated") {
    return <Navigate to={redirect} replace />;
  }

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const nextErrors = validateRegistration({
      username: username.trim(),
      email,
      password,
      confirmPassword,
    });
    setErrors(nextErrors);
    if (hasErrors(nextErrors)) {
      return;
    }
    mutation.mutate();
  };

  const serverErrors = isApiError(mutation.error) ? mutation.error.fieldErrors : {};

  return (
    <div className="w-full max-w-[30rem]">
      <div className="border border-white/10 bg-black/80 p-7 backdrop-blur-md sm:p-10">
        <h1 className="text-3xl font-bold text-white">Join CineRank</h1>
        <p className="mt-2 text-sm leading-relaxed text-white/60">
          Rate what you watch. We'll do the rest.
        </p>

        {mutation.isError ? (
          <div className="mt-5">
            <InlineNotice tone="error">
              {isApiError(mutation.error)
                ? mutation.error.message
                : "Couldn't create your account. Please try again."}
            </InlineNotice>
          </div>
        ) : null}

        <form className="mt-7 space-y-5" onSubmit={submit} noValidate>
          <TextField
            label="Username"
            name="username"
            autoComplete="username"
            value={username}
            onChange={(event) => {
              setUsername(event.target.value);
              setErrors((current) => ({ ...current, username: undefined }));
            }}
            error={errors.username ?? serverErrors.username}
            hint="3 to 64 letters, numbers, dots, underscores, or hyphens."
            required
          />
          <TextField
            label="Email (optional)"
            name="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => {
              setEmail(event.target.value);
              setErrors((current) => ({ ...current, email: undefined }));
            }}
            error={errors.email ?? serverErrors.email}
          />
          <TextField
            label="Password"
            name="password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(event) => {
              setPassword(event.target.value);
              setErrors((current) => ({ ...current, password: undefined }));
            }}
            error={errors.password ?? serverErrors.password}
            hint="At least 12 characters."
            required
          />
          <TextField
            label="Confirm password"
            name="confirmPassword"
            type="password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(event) => {
              setConfirmPassword(event.target.value);
              setErrors((current) => ({ ...current, confirmPassword: undefined }));
            }}
            error={errors.confirmPassword}
            required
          />
          <Button type="submit" className="mt-2 w-full" size="lg" loading={mutation.isPending}>
            Create account
          </Button>
        </form>

        <p className="mt-7 text-sm text-white/60">
          Already have an account?{" "}
          <Link
            to={`/login?redirect=${encodeURIComponent(redirect)}`}
            className="font-medium text-white underline underline-offset-4 hover:text-white/80"
          >
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
