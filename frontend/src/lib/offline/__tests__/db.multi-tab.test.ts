import "@/lib/offline/__tests__/setupFakeIndexedDb";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { clearOfflineDb, makeItemAnswer, makeLocalInspection } from "@/lib/offline/__tests__/fixtures";

/**
 * 🟠 Repro (revue orchestrateur, `.agent-team/review-j2.md` § 4 « Multi-onglets ») —
 * `inspectionWriteLocks` (`db.ts:86`) est une variable de MODULE : le mutex qui protège un
 * brouillon d'une course intra-onglet (`db.mutex.test.ts`, bug 🔴 n°1 de dev-frontend) ne
 * protège PLUS rien dès que deux onglets (PWA installée + onglet navigateur du même compte,
 * scénario banal) exécutent chacun leur propre instance du module `db.ts` — IndexedDB est
 * partagé par toute l'origine, mais le verrou en mémoire ne l'est pas.
 *
 * Reproduit ici en simulant deux onglets par deux instances de module JS SÉPARÉES
 * (`vi.resetModules()` entre les deux imports), partageant la MÊME base IndexedDB (globale au
 * processus, comme dans un vrai navigateur où les onglets partagent l'origine). Chaque
 * `updateInspection` reste atomique PAR INSTANCE ; rien ne le rend atomique ENTRE LES DEUX.
 */
describe("db.ts — 🟠 repro : mutex non partagé entre deux instances de module (\"deux onglets\")", () => {
  beforeEach(async () => {
    await clearOfflineDb();
  });

  it(
    "deux écritures concurrentes sur le même brouillon, une par « onglet », peuvent " +
      "s'écraser l'une l'autre (contrairement au cas mono-onglet, déjà protégé)",
    async () => {
      vi.resetModules();
      const tabA = await import("@/lib/offline/db");

      const draft = makeLocalInspection();
      await tabA.putInspection(draft);

      // « Onglet B » — nouvelle instance de module, donc nouveau `inspectionWriteLocks`,
      // vide, indépendant de celui de l'onglet A. Même base IndexedDB sous-jacente (globale).
      vi.resetModules();
      const tabB = await import("@/lib/offline/db");

      const answerA = makeItemAnswer();
      const answerB = makeItemAnswer();

      // Les deux écritures démarrent sans s'attendre — exactement le scénario de la revue :
      // une réponse de checklist tapée dans un onglet pendant qu'un tick de synchronisation
      // de l'AUTRE onglet est en train d'écrire.
      await Promise.all([
        tabA.updateInspection(draft.client_uuid, (current) => ({
          ...current,
          items: { ...current.items, [answerA.item_template_id]: answerA },
          items_dirty: true,
        })),
        tabB.updateInspection(draft.client_uuid, (current) => ({
          ...current,
          items: { ...current.items, [answerB.item_template_id]: answerB },
          items_dirty: true,
        })),
      ]);

      // État final vu par une troisième lecture (représente un rechargement de page, ou
      // simplement l'onglet A relisant après coup) — comportement SOUHAITÉ (pas garanti par
      // le code actuel) : les deux réponses devraient survivre, comme en mono-onglet.
      const final = await tabA.getInspection(draft.client_uuid);
      const itemKeys = Object.keys(final?.items ?? {});

      expect(itemKeys).toHaveLength(2);
      expect(final?.items[answerA.item_template_id]).toEqual(answerA);
      expect(final?.items[answerB.item_template_id]).toEqual(answerB);
    },
  );
});
