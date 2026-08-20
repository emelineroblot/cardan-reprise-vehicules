"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/error-state";
import { useAuth } from "@/lib/auth/AuthProvider";
import { homeRouteForRole } from "@/lib/auth/roles";
import { DEMO_ACCOUNTS } from "@/lib/auth/demo-accounts";

/**
 * Connexion en un clic (plan.md § 3.4) : 4 comptes de démo fixes, mots de passe publics
 * et affichés — assumé, données fictives sur base réinitialisée chaque nuit.
 */
export default function LoginPage() {
  const { login, status } = useAuth();
  const router = useRouter();
  const [pendingRole, setPendingRole] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  // Initialiseur paresseux plutôt qu'un effet : lu une seule fois, au montage, sans
  // déclencher de re-render en cascade (règle react-hooks/set-state-in-effect).
  const [nextPath] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    return new URLSearchParams(window.location.search).get("next");
  });

  useEffect(() => {
    if (status === "authenticated") {
      router.replace(nextPath || "/vehicules");
    }
  }, [status, nextPath, router]);

  const handleLogin = async (account: (typeof DEMO_ACCOUNTS)[number]) => {
    setError(null);
    setPendingRole(account.role);
    try {
      const user = await login(account.email, account.password);
      router.replace(nextPath || homeRouteForRole(user.role));
    } catch (err) {
      setError(err);
    } finally {
      setPendingRole(null);
    }
  };

  return (
    <div className="flex flex-1 flex-col items-center justify-center px-4 py-12">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle className="text-2xl">Connexion</CardTitle>
          <CardDescription>
            Démo cliquable — choisissez un rôle pour vous connecter instantanément. Identifiants
            publics, base de données réinitialisée chaque nuit.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {error ? <ErrorState error={error} title="Connexion impossible" /> : null}

          <div
            role="group"
            aria-label="Se connecter en tant que…"
            className="grid gap-3 sm:grid-cols-2"
          >
            {DEMO_ACCOUNTS.map((account) => (
              <Button
                key={account.role}
                type="button"
                variant="outline"
                disabled={pendingRole !== null}
                aria-busy={pendingRole === account.role}
                onClick={() => handleLogin(account)}
                className="h-auto flex-col items-start gap-1 whitespace-normal px-4 py-3 text-left"
              >
                <span className="text-sm font-semibold text-foreground">
                  Se connecter en tant que {account.label}
                </span>
                <span className="text-xs font-normal text-muted-foreground">
                  {account.description}
                </span>
                <span className="text-xs font-normal text-muted-foreground">
                  {account.email} · {account.password}
                </span>
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
