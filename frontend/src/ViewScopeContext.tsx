import {
  createContext,
  ReactNode,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { useAuth } from "./AuthContext";
import {
  getCurrentUserViewContext,
  UserViewContext,
  UserViewScope,
} from "./auth-api";

type ViewScopeState = {
  context: UserViewContext | null;
  scope: UserViewScope;
  loading: boolean;
  error: string | null;
  setScope: (scope: UserViewScope) => void;
};

const ViewScopeContext = createContext<ViewScopeState | null>(null);

export function ViewScopeProvider({ children }: { children: ReactNode }) {
  const { principal } = useAuth();
  const [context, setContext] = useState<UserViewContext | null>(null);
  const [scope, setScopeState] = useState<UserViewScope>("global");
  const [loading, setLoading] = useState(Boolean(principal));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!principal) {
      setContext(null);
      setScopeState("global");
      setLoading(false);
      setError(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    getCurrentUserViewContext(controller.signal)
      .then((value) => {
        setContext(value);
        setScopeState(value.view_policy.default_scope);
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setContext(null);
        setScopeState("global");
        setError(reason instanceof Error ? reason.message : "Impossible de charger le périmètre utilisateur.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [principal?.local_user_id, principal?.issuer, principal?.subject]);

  const value = useMemo<ViewScopeState>(() => ({
    context,
    scope,
    loading,
    error,
    setScope: (nextScope) => {
      if (!context?.view_policy.available_scopes.includes(nextScope)) return;
      setScopeState(nextScope);
    },
  }), [context, scope, loading, error]);

  return <ViewScopeContext.Provider value={value}>{children}</ViewScopeContext.Provider>;
}

export function useViewScope() {
  const context = useContext(ViewScopeContext);
  if (!context) throw new Error("useViewScope doit être utilisé sous ViewScopeProvider");
  return context;
}
