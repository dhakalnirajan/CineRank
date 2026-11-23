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
  validateLogin,
  type AuthFieldErrors,
} from "../features/auth/validation";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

export default function LoginPage() {
  useDocumentTitle("Sign in");
  const { status, signIn } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const redirect = safeRedirect(searchParams.get("redirect"));

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<AuthFieldErrors>({});

  const mutation = useMutation({
    mutationFn: (credentials: { username: string; password: string }) =>
      api.login(credentials.username, credentials.password),
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
    const nextErrors = validateLogin(username, password);
    setErrors(nextErrors);
    if (hasErrors(nextErrors)) {
      return;
    }
    mutation.mutate({ username: username.trim(), password });
  };

  const serverErrors = isApiError(mutation.error) ? mutation.error.fieldErrors : {};

  return (
    <div className="w-full max-w-[27rem]">
      <div className="border border-white/10 bg-black/80 p-7 backdrop-blur-md sm:p-10">
        <h1 className="text-3xl font-bold text-white">Welcome back</h1>
        <p className="mt-2 text-sm leading-relaxed text-white/60">
          See recommendations shaped by your ratings and watchlist.
        </p>

        {mutation.isError ? (
          <div className="mt-5">
            <InlineNotice tone="error">
              {isApiError(mutation.error)
                ? mutation.error.status === 401
                  ? "Incorrect username or password."
                  : mutation.error.message
                : "Sign in failed. Try again."}
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
            required
          />
          <TextField
            label="Password"
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => {
              setPassword(event.target.value);
              setErrors((current) => ({ ...current, password: undefined }));
            }}
            error={errors.password ?? serverErrors.password}
            required
          />
          <div className="flex justify-end">
            <Link
              to="/forgot-password"
              className="text-sm text-white/55 underline underline-offset-4 hover:text-white"
            >
              Forgot password?
            </Link>
          </div>
          <Button type="submit" className="mt-2 w-full" size="lg" loading={mutation.isPending}>
            Sign in
          </Button>
        </form>

        <p className="mt-7 text-sm text-white/60">
          New to CineRank?{" "}
          <Link
            to={`/register?redirect=${encodeURIComponent(redirect)}`}
            className="font-medium text-white underline underline-offset-4 hover:text-white/80"
          >
            Create an account
          </Link>
        </p>
      </div>
      <p className="mt-5 text-center text-xs leading-relaxed text-white/35">
        Using a shared device? Sign out when you're done.
      </p>
    </div>
  );
}
