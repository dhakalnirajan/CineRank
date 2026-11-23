import { Component, type ErrorInfo, type ReactNode } from "react";
import { buttonClasses } from "../ui/Button";
import { ErrorPage } from "./ErrorPage";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    if (import.meta.env.DEV) {
      console.error("Unhandled render error", error, info.componentStack);
    }
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <ErrorPage
          code="500"
          title="Something went wrong"
          message="This page couldn't be displayed. Reload to try again, or head back home."
          actions={
            <>
              <button
                type="button"
                onClick={() => window.location.reload()}
                className={buttonClasses("primary", "md")}
              >
                Reload
              </button>
              <a href="/" className={buttonClasses("secondary", "md")}>
                Back to home
              </a>
            </>
          }
        />
      );
    }
    return this.props.children;
  }
}
