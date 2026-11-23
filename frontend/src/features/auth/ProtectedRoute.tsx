import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { PageLoader } from "../../components/feedback/PageLoader";
import { ErrorState } from "../../components/feedback/ErrorState";
import { useAuth } from "./AuthProvider";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { status, retryUser } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return <PageLoader label="Checking your session" />;
  }

  if (status === "error") {
    return (
      <div className="page-shell py-16">
        <ErrorState
          title="We couldn't load your account"
          message="Please try again in a moment."
          onRetry={retryUser}
        />
      </div>
    );
  }

  if (status === "anonymous") {
    const redirect = `${location.pathname}${location.search}`;
    return <Navigate to={`/login?redirect=${encodeURIComponent(redirect)}`} replace />;
  }

  return <>{children}</>;
}

export function safeRedirect(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) {
    return "/";
  }
  return value;
}
