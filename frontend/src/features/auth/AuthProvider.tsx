import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { api } from "../../api/endpoints";
import { isApiError } from "../../api/errors";
import { queryKeys } from "../../api/queryKeys";
import { refreshAccessToken } from "../../api/session";
import { sessionHint, tokenStore } from "../../api/token";
import type { TokenResponse, User } from "../../types/api";

export type AuthStatus = "loading" | "authenticated" | "anonymous" | "error";

type BootstrapState = "checking" | "ready" | "failed";

interface AuthContextValue {
  status: AuthStatus;
  user: User | null;
  token: string | null;
  signIn: (session: TokenResponse) => void;
  signOut: () => void;
  retryUser: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function accessTokenExpiryMs(rawToken: string): number | null {
  try {
    const payload = rawToken.split(".")[1];
    if (!payload) return null;
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const decoded = JSON.parse(window.atob(normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "="))) as { exp?: unknown };
    return typeof decoded.exp === "number" ? decoded.exp * 1000 : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [token, setToken] = useState<string | null>(() => tokenStore.get());
  const [bootstrapState, setBootstrapState] = useState<BootstrapState>(() => {
    if (tokenStore.get()) return "ready";
    return sessionHint.get() ? "checking" : "ready";
  });
  const shouldBootstrapOnMount = useRef(
    !tokenStore.get() && sessionHint.get(),
  );

  useEffect(() => tokenStore.subscribe(setToken), []);

  useEffect(() => {
    if (!token) return;
    let lastActivity = Date.now();
    const markActivity = () => {
      if (document.visibilityState === "visible") lastActivity = Date.now();
    };
    const activityEvents: Array<keyof WindowEventMap> = ["pointerdown", "keydown", "touchstart", "scroll"];
    activityEvents.forEach((eventName) => window.addEventListener(eventName, markActivity, { passive: true }));
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "visible") return;
      if (Date.now() - lastActivity > 30 * 60_000) return;
      const expiresAt = accessTokenExpiryMs(token);
      if (expiresAt !== null && expiresAt - Date.now() <= 5 * 60_000) {
        void refreshAccessToken().catch(() => undefined);
      }
    }, 30_000);
    document.addEventListener("visibilitychange", markActivity);
    return () => {
      window.clearInterval(timer);
      activityEvents.forEach((eventName) => window.removeEventListener(eventName, markActivity));
      document.removeEventListener("visibilitychange", markActivity);
    };
  }, [token]);

  const clearSession = useCallback(() => {
    tokenStore.clear();
    queryClient.clear();
    setBootstrapState("ready");
  }, [queryClient]);

  const signOut = useCallback(() => {
    void api.logout().catch(() => undefined);
    clearSession();
  }, [clearSession]);

  useEffect(() => {
    const handleUnauthorized = () => clearSession();
    window.addEventListener("cinerank:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("cinerank:unauthorized", handleUnauthorized);
  }, [clearSession]);

  const bootstrap = useCallback(async () => {
    setBootstrapState("checking");
    try {
      await refreshAccessToken();
      setBootstrapState("ready");
    } catch {
      setBootstrapState("failed");
    }
  }, []);

  useEffect(() => {
    if (shouldBootstrapOnMount.current) {
      shouldBootstrapOnMount.current = false;
      void bootstrap();
    }
  }, [bootstrap]);

  const userQuery = useQuery({
    queryKey: queryKeys.me,
    queryFn: ({ signal }) => api.me(signal),
    enabled: Boolean(token),
    retry: false,
    staleTime: 5 * 60_000,
  });

  useEffect(() => {
    if (isApiError(userQuery.error) && userQuery.error.status === 401) {
      clearSession();
    }
  }, [userQuery.error, clearSession]);

  const signIn = useCallback(
    (nextSession: TokenResponse) => {
      setBootstrapState("ready");
      queryClient.clear();
      tokenStore.set(nextSession.access_token);
    },
    [queryClient],
  );

  const retryUser = useCallback(() => {
    if (!tokenStore.get()) {
      void bootstrap();
      return;
    }
    void userQuery.refetch();
  }, [bootstrap, userQuery]);

  const value = useMemo<AuthContextValue>(() => {
    const user = token ? (userQuery.data ?? null) : null;
    let status: AuthStatus;
    if (bootstrapState === "checking") {
      status = "loading";
    } else if (bootstrapState === "failed" && !token) {
      status = "error";
    } else if (!token) {
      status = "anonymous";
    } else if (user) {
      status = "authenticated";
    } else if (userQuery.isError) {
      status = "error";
    } else {
      status = "loading";
    }
    return { status, user, token, signIn, signOut, retryUser };
  }, [bootstrapState, token, userQuery.data, userQuery.isError, signIn, signOut, retryUser]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
