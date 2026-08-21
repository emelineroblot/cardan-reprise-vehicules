"use client";

import { useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { ApiError } from "@/lib/api/client";
import { AuthProvider } from "@/lib/auth/AuthProvider";

/**
 * SPA authentifiée derrière TanStack Query (plan.md § 4 décision H) : un seul chemin
 * de données côté client pour les 3 jalons, y compris le cache/rejeu de mutations
 * qu'exigera le mode terrain de J2.
 */
export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: (failureCount, error) => {
              if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
                return false;
              }
              return failureCount < 2;
            },
          },
          mutations: {
            retry: false,
          },
        },
      }),
  );

  return (
    // `attribute="class"` bascule la classe `.dark` déjà consommée par globals.css (palette
    // clair/sombre + dataviz, skill `dataviz`) ; `disableTransitionOnChange` évite un flash de
    // transition CSS sur toute la page au changement de thème.
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>{children}</AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
