"use client";

import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api/client";
import type { AppUser } from "@/lib/api/types";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  user: AppUser | null;
  status: AuthStatus;
  error: unknown;
  login: (email: string, password: string) => Promise<AppUser>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const ME_QUERY_KEY = ["auth", "me"] as const;

/** Établit la session courante via `GET /auth/me` (plan.md § 6 vague 2). */
export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  const meQuery = useQuery<AppUser, unknown>({
    queryKey: ME_QUERY_KEY,
    queryFn: () => api.get<AppUser>("/auth/me"),
    retry: false,
    refetchOnWindowFocus: false,
  });

  const loginMutation = useMutation({
    mutationFn: async ({ email, password }: { email: string; password: string }) => {
      // Contrat figé (implementation.md § Backend « Contrat final ») : POST /auth/login
      // renvoie l'utilisateur À PLAT (MeResponse), identique à GET /auth/me — jamais
      // d'enveloppe { user: ... }.
      return api.post<AppUser>("/auth/login", { email, password });
    },
    onSuccess: (user) => {
      queryClient.setQueryData(ME_QUERY_KEY, user);
    },
  });

  const logoutMutation = useMutation({
    mutationFn: () => api.post<void>("/auth/logout"),
    onSuccess: () => {
      queryClient.setQueryData(ME_QUERY_KEY, null);
      queryClient.clear();
    },
  });

  const login = useCallback(
    async (email: string, password: string) => loginMutation.mutateAsync({ email, password }),
    [loginMutation],
  );

  const logout = useCallback(async () => {
    await logoutMutation.mutateAsync();
  }, [logoutMutation]);

  const status: AuthStatus = meQuery.isPending
    ? "loading"
    : meQuery.data
      ? "authenticated"
      : "unauthenticated";

  const value = useMemo<AuthContextValue>(
    () => ({
      user: meQuery.data ?? null,
      status,
      error: meQuery.error,
      login,
      logout,
    }),
    [meQuery.data, status, meQuery.error, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth doit être utilisé sous <AuthProvider>.");
  }
  return ctx;
}

export function isSessionExpired(error: unknown): boolean {
  return error instanceof ApiError && error.isUnauthenticated;
}
