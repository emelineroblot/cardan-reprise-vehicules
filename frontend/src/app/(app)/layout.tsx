"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth/AuthProvider";
import { AppNav } from "@/components/domain/AppNav";
import { LoadingState } from "@/components/ui/loading-state";

/**
 * Coquille de la SPA authentifiée (plan.md § 4 décision H). Le middleware ne fait que
 * rediriger si le cookie est absent (confort) ; ici, `GET /auth/me` fait foi côté client
 * et referme la fenêtre où un cookie périmé laisserait voir un écran vide.
 */
export default function AppShellLayout({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/login");
    }
  }, [status, router]);

  if (status === "loading") {
    return (
      <div className="flex flex-1 items-center justify-center">
        <LoadingState label="Vérification de la session…" />
      </div>
    );
  }

  if (status === "unauthenticated") {
    // Redirection en cours (effet ci-dessus) : rien à afficher.
    return null;
  }

  return (
    <div className="flex min-h-full flex-1 flex-col">
      <AppNav />
      <main id="contenu-principal" className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        {children}
      </main>
    </div>
  );
}
