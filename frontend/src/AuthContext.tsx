import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from "react";

import { ApiError } from "./api";
import { AuthPrincipal, getCurrentPrincipal } from "./auth-api";

type AuthState = {
  principal: AuthPrincipal | null;
  loading: boolean;
  error: string | null;
  can: (permission: string) => boolean;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [principal, setPrincipal] = useState<AuthPrincipal | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    getCurrentPrincipal(controller.signal)
      .then(setPrincipal)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        if (reason instanceof ApiError) {
          setError(`${reason.message}${reason.code ? ` (${reason.code})` : ""}`);
          return;
        }
        setError(reason instanceof Error ? reason.message : "Impossible de charger l’identité courante.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  const value = useMemo<AuthState>(() => ({
    principal,
    loading,
    error,
    can: (permission: string) => Boolean(principal?.permissions.includes(permission)),
  }), [principal, loading, error]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth doit être utilisé sous AuthProvider");
  return context;
}
