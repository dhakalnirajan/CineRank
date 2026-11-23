import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import { ErrorBoundary } from "../components/feedback/ErrorBoundary";
import { PageLoader } from "../components/feedback/PageLoader";
import { AppShell } from "../components/layout/AppShell";
import { ProtectedRoute } from "../features/auth/ProtectedRoute";
import { IntroScreen } from "../features/intro/IntroScreen";
import { AuthLayout } from "../layouts/AuthLayout";

const HomePage = lazy(() => import("../pages/HomePage"));
const ExplorePage = lazy(() => import("../pages/ExplorePage"));
const GenreGuidePage = lazy(() => import("../pages/GenreGuidePage"));
const SearchPage = lazy(() => import("../pages/SearchPage"));
const TitlePage = lazy(() => import("../pages/TitlePage"));
const LegacyTitlePage = lazy(() => import("../pages/LegacyTitlePage"));
const WatchlistPage = lazy(() => import("../pages/WatchlistPage"));
const RecommendationsPage = lazy(() => import("../pages/RecommendationsPage"));
const HistoryPage = lazy(() => import("../pages/HistoryPage"));
const ProfilePage = lazy(() => import("../pages/ProfilePage"));
const PreferencesPage = lazy(() => import("../pages/PreferencesPage"));
const LoginPage = lazy(() => import("../pages/LoginPage"));
const RegisterPage = lazy(() => import("../pages/RegisterPage"));
const ForgotPasswordPage = lazy(() => import("../pages/ForgotPasswordPage"));
const ResetPasswordPage = lazy(() => import("../pages/ResetPasswordPage"));
const VerifyEmailPage = lazy(() => import("../pages/VerifyEmailPage"));
const NotFoundPage = lazy(() => import("../pages/NotFoundPage"));

export function App() {
  return (
    <ErrorBoundary>
      <IntroScreen />
      <Suspense fallback={<PageLoader label="Loading CineRank" />}>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<HomePage />} />
            <Route path="explore" element={<ExplorePage />} />
            <Route path="genres" element={<GenreGuidePage />} />
            <Route path="search" element={<SearchPage />} />
            <Route
              path="recommendations"
              element={
                <ProtectedRoute>
                  <RecommendationsPage />
                </ProtectedRoute>
              }
            />
            <Route path="movie/:serialNumber" element={<TitlePage mediaType="movie" />} />
            <Route path="tv/:serialNumber" element={<TitlePage mediaType="tv" />} />
            <Route path="title/:titleId" element={<LegacyTitlePage />} />
            <Route
              path="watchlist"
              element={
                <ProtectedRoute>
                  <WatchlistPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="history"
              element={
                <ProtectedRoute>
                  <HistoryPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="profile"
              element={
                <ProtectedRoute>
                  <ProfilePage />
                </ProtectedRoute>
              }
            />
            <Route
              path="preferences"
              element={
                <ProtectedRoute>
                  <PreferencesPage />
                </ProtectedRoute>
              }
            />
            <Route path="*" element={<NotFoundPage />} />
          </Route>

          <Route element={<AuthLayout />}>
            <Route path="login" element={<LoginPage />} />
            <Route path="register" element={<RegisterPage />} />
            <Route path="forgot-password" element={<ForgotPasswordPage />} />
            <Route path="reset-password" element={<ResetPasswordPage />} />
            <Route path="verify-email" element={<VerifyEmailPage />} />
          </Route>
        </Routes>
      </Suspense>
    </ErrorBoundary>
  );
}
