import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { isApiError } from "../api/errors";
import { InlineNotice } from "../components/feedback/InlineNotice";
import { Button } from "../components/ui/Button";
import { TextField } from "../components/ui/TextField";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

export default function ResetPasswordPage() {
  useDocumentTitle("Choose a new password");
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [errors, setErrors] = useState<{ password?: string; confirmPassword?: string }>({});

  const mutation = useMutation({
    mutationFn: (newPassword: string) => api.resetPassword(token, newPassword),
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const nextErrors: { password?: string; confirmPassword?: string } = {};
    if (password.length < 12) {
      nextErrors.password = "Use at least 12 characters.";
    }
    if (confirmPassword !== password) {
      nextErrors.confirmPassword = "Passwords do not match.";
    }
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      return;
    }
    mutation.mutate(password);
  };

  if (!token) {
    return (
      <div className="w-full max-w-[27rem]">
        <div className="border border-white/10 bg-black/80 p-7 backdrop-blur-md sm:p-10">
          <h1 className="text-3xl font-bold text-white">Link not valid</h1>
          <p className="mt-2 text-sm leading-relaxed text-white/60">
            This reset link is missing or incomplete. Request a new one to continue.
          </p>
          <Link
            to="/forgot-password"
            className="mt-6 inline-flex h-12 w-full items-center justify-center rounded-control bg-accent font-semibold text-accent-ink transition-colors hover:bg-accent-strong"
          >
            Request a new link
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-[27rem]">
      <div className="border border-white/10 bg-black/80 p-7 backdrop-blur-md sm:p-10">
        <h1 className="text-3xl font-bold text-white">Choose a new password</h1>
        <p className="mt-2 text-sm leading-relaxed text-white/60">
          You'll be signed out everywhere once your password is updated.
        </p>

        {mutation.isSuccess ? (
          <div className="mt-5 space-y-5">
            <InlineNotice tone="success">Your password has been updated.</InlineNotice>
            <Link
              to="/login"
              className="inline-flex h-12 w-full items-center justify-center rounded-control bg-accent font-semibold text-accent-ink transition-colors hover:bg-accent-strong"
            >
              Sign in
            </Link>
          </div>
        ) : (
          <>
            {mutation.isError ? (
              <div className="mt-5">
                <InlineNotice tone="error">
                  {isApiError(mutation.error) && mutation.error.status === 400
                    ? "This reset link is invalid or has expired."
                    : isApiError(mutation.error)
                      ? mutation.error.message
                      : "Couldn't update your password right now. Please try again."}
                </InlineNotice>
              </div>
            ) : null}

            <form className="mt-7 space-y-5" onSubmit={submit} noValidate>
              <TextField
                label="New password"
                name="password"
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value);
                  setErrors((current) => ({ ...current, password: undefined }));
                }}
                error={errors.password}
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
                Save new password
              </Button>
            </form>

            {isApiError(mutation.error) && mutation.error.status === 400 ? (
              <p className="mt-5 text-sm text-white/60">
                <Link
                  to="/forgot-password"
                  className="font-medium text-white underline underline-offset-4 hover:text-white/80"
                >
                  Request a new link
                </Link>
              </p>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
