import { useQuery } from "@tanstack/react-query";
import { Navigate, useParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { isApiError } from "../api/errors";
import { queryKeys } from "../api/queryKeys";
import { ErrorState } from "../components/feedback/ErrorState";
import { PageLoader } from "../components/feedback/PageLoader";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { getTitleUrl } from "../utils/titleRoute";
import NotFoundPage from "./NotFoundPage";

export default function LegacyTitlePage() {
  const { titleId = "" } = useParams();
  const titleQuery = useQuery({
    queryKey: queryKeys.legacyTitle(titleId),
    queryFn: ({ signal }) => api.getMovie(titleId, signal),
    enabled: Boolean(titleId),
    retry: false,
  });

  useDocumentTitle(titleQuery.data?.title ?? "Title");

  if (!titleId || (titleQuery.isError && isApiError(titleQuery.error) && titleQuery.error.status === 404)) {
    return <NotFoundPage />;
  }
  if (titleQuery.isLoading) {
    return <PageLoader label="Finding that title" />;
  }
  if (titleQuery.isError || !titleQuery.data) {
    return (
      <div className="page-shell py-20">
        <ErrorState
          title="We couldn't load this title"
          message={
            isApiError(titleQuery.error)
              ? titleQuery.error.message
              : "Please try again in a moment."
          }
          onRetry={() => void titleQuery.refetch()}
        />
      </div>
    );
  }

  return <Navigate to={getTitleUrl(titleQuery.data)} replace />;
}
