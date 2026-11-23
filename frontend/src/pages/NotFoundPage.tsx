import { Link } from "react-router-dom";
import { ErrorPage } from "../components/feedback/ErrorPage";
import { buttonClasses } from "../components/ui/Button";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

export default function NotFoundPage() {
  useDocumentTitle("Page not found");

  return (
    <ErrorPage
      code="404"
      title="This page doesn't exist"
      message="That link may be wrong, or the title may have left the catalogue."
      actions={
        <>
          <Link to="/" className={buttonClasses("primary", "md")}>
            Back to home
          </Link>
          <Link to="/explore" className={buttonClasses("secondary", "md")}>
            Browse the catalogue
          </Link>
        </>
      }
    />
  );
}
