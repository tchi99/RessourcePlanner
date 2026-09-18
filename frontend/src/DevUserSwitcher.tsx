import { useEffect, useMemo, useState } from "react";

import { useAuth } from "./AuthContext";
import {
  DevUserSwitcherState,
  getDevUserSwitcher,
  resetDevUser,
  selectDevUser,
} from "./auth-api";

const BOOTSTRAP_VALUE = "__bootstrap__";

export default function DevUserSwitcher() {
  const { principal } = useAuth();
  const [state, setState] = useState<DevUserSwitcherState | null>(null);
  const [switching, setSwitching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getDevUserSwitcher(controller.signal)
      .then(setState)
      .catch(() => setState(null));
    return () => controller.abort();
  }, []);

  const currentValue = useMemo(() => {
    if (!principal?.local_user_id) return BOOTSTRAP_VALUE;
    if (state?.users.some((user) => user.user_id === principal.local_user_id)) {
      return principal.local_user_id;
    }
    return BOOTSTRAP_VALUE;
  }, [principal?.local_user_id, state]);

  if (!state?.enabled) return null;

  async function changeIdentity(userId: string) {
    setSwitching(true);
    setError(null);
    try {
      if (userId === BOOTSTRAP_VALUE) {
        await resetDevUser();
      } else {
        await selectDevUser(userId);
      }
      window.location.reload();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Impossible de changer d’identité.");
      setSwitching(false);
    }
  }

  return (
    <div className="dev-user-switcher">
      <label>
        <span>Identité de test</span>
        <select
          aria-label="Identité de test"
          value={currentValue}
          disabled={switching}
          onChange={(event) => void changeIdentity(event.target.value)}
        >
          <option value={BOOTSTRAP_VALUE}>
            {state.bootstrap.display_name} — {state.bootstrap.roles.join(" · ")}
          </option>
          {state.users.map((user) => (
            <option value={user.user_id} key={user.user_id}>
              {user.display_name} — {user.roles.join(" · ")}
            </option>
          ))}
        </select>
      </label>
      {error && <small role="alert">{error}</small>}
    </div>
  );
}
