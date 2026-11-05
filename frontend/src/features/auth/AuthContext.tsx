import { useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { ApiError, apiGet, apiPost, onSessionEvent, setAccessToken, setRefreshHandler } from "@/lib/api";

import type { Me, SetupStatus, TokenResponse } from "./types";

export type AuthStatus = "loading" | "setup" | "anonymous" | "authenticated";

interface AuthState {
  status: AuthStatus;
  user: Me | null;
  /** Shown on the login page after an involuntary sign-out. */
  notice: string | null;
  /** True after the user chose to sign out: the guard then does not remember the page. */
  signedOutByUser: boolean;
}

interface AuthContextValue extends AuthState {
  login: (username: string, password: string) => Promise<Me>;
  logout: () => Promise<void>;
  changePassword: (current: string, next: string) => Promise<Me>;
  /** Adopt a session returned by another endpoint (first-run setup). */
  acceptSession: (token: TokenResponse) => void;
  can: (permission: string) => boolean;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

async function refreshSession(): Promise<TokenResponse | null> {
  try {
    return await apiPost<TokenResponse>("/auth/refresh", undefined, { anonymous: true });
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return null;
    throw err;
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [state, setState] = React.useState<AuthState>({ status: "loading", user: null, notice: null, signedOutByUser: false });

  const adopt = React.useCallback((token: TokenResponse) => {
    setAccessToken(token.access_token);
    setState({ status: "authenticated", user: token.user, notice: null, signedOutByUser: false });
  }, []);

  const signedOut = React.useCallback(
    (notice: string | null, byUser = false) => {
      setAccessToken(null);
      queryClient.clear();
      setState({ status: "anonymous", user: null, notice, signedOutByUser: byUser });
    },
    [queryClient],
  );

  React.useEffect(() => {
    setRefreshHandler(async () => {
      const token = await refreshSession();
      if (!token) return null;
      setAccessToken(token.access_token);
      setState((s) => ({ ...s, user: token.user }));
      return token.access_token;
    });
    const off = onSessionEvent((event) => {
      if (event === "expired") signedOut("Your session ended. Please sign in again.");
      if (event === "password_change_required") {
        setState((s) => (s.user ? { ...s, user: { ...s.user, must_change_password: true } } : s));
      }
    });
    return () => {
      off();
      setRefreshHandler(null);
    };
  }, [signedOut]);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const setup = await apiGet<SetupStatus>("/setup/status");
        if (cancelled) return;
        if (setup.needs_setup) {
          setState({ status: "setup", user: null, notice: null, signedOutByUser: false });
          return;
        }
        const token = await refreshSession();
        if (cancelled) return;
        if (token) adopt(token);
        else setState({ status: "anonymous", user: null, notice: null, signedOutByUser: false });
      } catch {
        if (!cancelled) setState({ status: "anonymous", user: null, notice: "The FabTrack server could not be reached.", signedOutByUser: false });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [adopt]);

  const value = React.useMemo<AuthContextValue>(
    () => ({
      ...state,
      login: async (username, password) => {
        const token = await apiPost<TokenResponse>("/auth/login", { username, password }, { anonymous: true });
        adopt(token);
        return token.user;
      },
      logout: async () => {
        try {
          await apiPost<undefined>("/auth/logout", undefined, { anonymous: true });
        } finally {
          signedOut(null, true);
        }
      },
      changePassword: async (current, next) => {
        const token = await apiPost<TokenResponse>("/auth/change-password", { current_password: current, new_password: next });
        adopt(token);
        return token.user;
      },
      acceptSession: adopt,
      can: (permission) => state.user?.permissions.includes(permission) ?? false,
    }),
    [state, adopt, signedOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = React.useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

/** True if the signed-in user holds the permission. UI hides what the user cannot do;
 *  the server enforces it regardless. */
export function useCan(permission: string): boolean {
  return useAuth().can(permission);
}
