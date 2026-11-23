import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, tokenStore } from "@/services/api";
import type { RoleCode, User } from "@/types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => void;
  hasRole: (...roles: RoleCode[]) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!tokenStore.get()) {
      setLoading(false);
      return;
    }
    api
      .get<User>("/auth/me")
      .then(setUser)
      .catch(() => tokenStore.clear())
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.post<{ access_token: string; user: User }>("/auth/token", { email, password });
    tokenStore.set(res.access_token);
    setUser(res.user);
    return res.user;
  }, []);

  const logout = useCallback(() => {
    tokenStore.clear();
    setUser(null);
    window.location.href = "/login";
  }, []);

  const hasRole = useCallback((...roles: RoleCode[]) => !!user && roles.some((r) => user.roles.includes(r)), [user]);

  const value = useMemo(() => ({ user, loading, login, logout, hasRole }), [user, loading, login, logout, hasRole]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

/** Landing page per role. */
export function homeFor(user: User): string {
  if (user.roles.includes("PARTNER")) return "/partner";
  if (user.roles.includes("PROJECT_MANAGER") || user.roles.includes("FINANCE_OFFICER")) return "/exceptions";
  return "/dashboard";
}
