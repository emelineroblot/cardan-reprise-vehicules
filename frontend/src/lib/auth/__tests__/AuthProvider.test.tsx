import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "@/lib/auth/AuthProvider";

/**
 * Test de contrat — écrit par `dev-tester` en intégration (vague 5), après avoir constaté
 * l'échec réel de `frontend/e2e/j1-saisie.spec.ts` (le parcours reste bloqué sur `/login`).
 *
 * Le corps de réponse ci-dessous n'est PAS inventé : c'est la sortie réelle observée en
 * exécutant `curl -X POST http://127.0.0.1:8000/api/v1/auth/login` contre le backend réel
 * (`backend/app/api/v1/auth.py`, `response_model=MeResponse`) le 2026-08-20. Voir
 * `.agent-team/tests.md` § Échecs & causes.
 */
function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("AuthProvider.login — contrat réel de POST /auth/login", () => {
  it("expose un utilisateur avec un rôle défini à partir de la réponse réelle du backend", async () => {
    // Réponse RÉELLE (curl, 2026-08-20) : l'utilisateur est renvoyé À PLAT par le backend,
    // jamais enveloppé sous `{ user: ... }`.
    const flatUserResponseFromBackend = {
      id: "ca2e7b36-1e8f-46ad-90a2-5a429c7c521e",
      email: "operatrice@cardan.demo",
      full_name: "Claire Dubois",
      role: "operatrice",
      telephone: "0601020304",
    };

    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/auth/me")) {
        return jsonResponse(
          { error: { code: "unauthenticated", message: "Non authentifié." } },
          401,
        );
      }
      if (url.endsWith("/auth/login")) {
        return jsonResponse(flatUserResponseFromBackend, 200);
      }
      throw new Error(`URL non mockée dans ce test : ${url}`);
    });

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>
        <AuthProvider>{children}</AuthProvider>
      </QueryClientProvider>
    );

    const { result } = renderHook(() => useAuth(), { wrapper });

    await waitFor(() => expect(result.current.status).toBe("unauthenticated"));

    const user = await act(async () =>
      result.current.login("operatrice@cardan.demo", "demo1234"),
    );

    // Bug d'intégration réel : `AuthProvider.tsx` lit `res.user`, mais le backend renvoie
    // l'utilisateur à plat. `user` vaut donc `undefined` avec le code actuel — c'est
    // exactement ce qui bloque `frontend/e2e/j1-saisie.spec.ts` sur `/login`.
    expect(user).toBeDefined();
    expect(user?.role).toBe("operatrice");

    fetchSpy.mockRestore();
  });
});
