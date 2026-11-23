import { useMutation } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { isApiError } from "../api/errors";
import { InlineNotice } from "../components/feedback/InlineNotice";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

export default function VerifyEmailPage() {
  useDocumentTitle("Confirm email");
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const started = useRef(false);

  const mutation = useMutation({
    mutationFn: (value: string) => api.verifyEmail(value),
  });

  useEffect(() => {
    if (!token || started.current) {
      return;
    }
    started.current = true;
    mutation.mutate(token);
  }, [mutation, token]);

  const invalid = !token || mutation.isError;
  const status = !token ? "missing" : mutation.isSuccess ? "success" : invalid ? "error" : "loading";

  return (
    <div className="w-full max-w-[27rem]">
      <div className="border border-white/10 bg-black/80 p-7 backdrop-blur-md sm:p-10">
        <h1 className="text-3xl font-bold text-white">
          {status === "success" ? "Email confirmed" : "Confirm your email"}
        </h1>

        {status === "loading" ? (
          <p className="mt-2 text-sm leading-relaxed text-white/60">Checking your link.</p>
        ) : null}

        {status === "success" ? (
          <>
            <p className="mt-2 text-sm leading-relaxed text-white/60">
              Your email address is confirmed. You're all set.
            </p>
            <Link
              to="/"
              className="mt-6 inline-flex h-12 w-full items-center justify-center rounded-control bg-accent font-semibold text-accent-ink transition-colors hover:bg-accent-strong"
            >
              Start exploring
            </Link>
          </>
        ) : null}

        {status === "error" ? (
          <div className="mt-5">
            <InlineNotice tone="error">
              {isApiError(mutation.error) && mutation.error.status !== 400
                ? mutation.error.message
                : "This confirmation link is invalid or has expired."}
            </InlineNotice>
          </div>
        ) : null}

        {status === "missing" ? (
          <p className="mt-2 text-sm leading-relaxed text-white/60">
            This confirmation link is missing or incomplete.
          </p>
        ) : null}

        {invalid ? (
          <p className="mt-5 text-sm text-white/60">
            <Link
              to="/profile"
              className="font-medium text-white underline underline-offset-4 hover:text-white/80"
            >
              Resend from your profile
            </Link>
          </p>
        ) : null}
      </div>
    </div>
  );
}
