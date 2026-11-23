import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/endpoints";
import { isApiError } from "../api/errors";
import { InlineNotice } from "../components/feedback/InlineNotice";
import { Button } from "../components/ui/Button";
import { TextField } from "../components/ui/TextField";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function ForgotPasswordPage() {
  useDocumentTitle("Reset password");
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (address: string) => api.forgotPassword(address),
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = email.trim();
    if (!EMAIL_PATTERN.test(trimmed)) {
      setError("Enter the email address on your account.");
      return;
    }
    setError(null);
    mutation.mutate(trimmed);
  };

  return (
    <div className="w-full max-w-[27rem]">
      <div className="border border-white/10 bg-black/80 p-7 backdrop-blur-md sm:p-10">
        <h1 className="text-3xl font-bold text-white">Reset your password</h1>
        <p className="mt-2 text-sm leading-relaxed text-white/60">
          Enter your email and we'll send a link to choose a new password.
        </p>

        {mutation.isSuccess ? (
          <div className="mt-5">
            <InlineNotice tone="success">
              If that email is on an account, a reset link is on its way.
            </InlineNotice>
          </div>
        ) : null}

        {mutation.isError ? (
          <div className="mt-5">
            <InlineNotice tone="error">
              {isApiError(mutation.error)
                ? mutation.error.message
                : "Couldn't send the link right now. Please try again."}
            </InlineNotice>
          </div>
        ) : null}

        <form className="mt-7 space-y-5" onSubmit={submit} noValidate>
          <TextField
            label="Email"
            name="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => {
              setEmail(event.target.value);
              setError(null);
            }}
            error={error ?? undefined}
            required
          />
          <Button type="submit" className="mt-2 w-full" size="lg" loading={mutation.isPending}>
            Send reset link
          </Button>
        </form>

        <p className="mt-7 text-sm text-white/60">
          Remembered it?{" "}
          <Link
            to="/login"
            className="font-medium text-white underline underline-offset-4 hover:text-white/80"
          >
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
