import "fake-indexeddb/auto";
import { beforeEach, describe, expect, it } from "vitest";
import { getInspection, putInspection, updateInspection } from "@/lib/offline/db";
import { upsertItemAnswer } from "@/lib/offline/draft";
import { makeItemAnswer, makeLocalInspection } from "@/lib/offline/__tests__/fixtures";

/**
 * Reproduction directe du bug 🔴 n°1 consigné dans implementation.md § J2 Frontend
 * (« Perte silencieuse de réponses de checklist — écriture locale ») : deux mutations
 * concurrentes du MÊME brouillon (deux cases cochées coup sur coup) écrasaient l'une l'autre
 * quand chacune faisait un `getInspection` + `putInspection` isolé. Ce fichier prouve que le
 * mutex `updateInspection` (`db.ts`) empêche réellement la course — pas seulement en apparence
 * (pas de simple vérification qu'un drapeau passe à `true`), mais en relisant l'état final
 * réellement persisté en IndexedDB.
 */
describe("db.updateInspection — mutex par brouillon", () => {
  beforeEach(async () => {
    // IndexedDB (fake) n'est pas vidée automatiquement entre tests : chaque test utilise un
    // client_uuid généré (compteur de fixtures.ts), donc pas de collision, mais on garde ce
    // rappel explicite plutôt qu'un `afterEach` qui masquerait une éventuelle fuite d'état.
  });

  it("ne perd aucune des deux écritures concurrentes lancées sans attendre la première (repro bug n°1)", async () => {
    const draft = makeLocalInspection();
    await putInspection(draft);

    const answerA = makeItemAnswer();
    const answerB = makeItemAnswer();

    // Les DEUX écritures démarrent avant que la première n'ait fini — c'est précisément le
    // scénario « chauffeur rapide » ou « saisie + tick de synchronisation en même temps ».
    // Sans mutex : la seconde lit l'état AVANT l'écriture de la première puis l'écrase.
    const [resultA, resultB] = await Promise.all([
      upsertItemAnswer(draft.client_uuid, answerA),
      upsertItemAnswer(draft.client_uuid, answerB),
    ]);

    // Chaque appel doit lui-même renvoyer un état qui contient AU MOINS sa propre écriture.
    expect(resultA.items[answerA.item_template_id]).toEqual(answerA);
    expect(resultB.items[answerB.item_template_id]).toEqual(answerB);

    // Et surtout : l'état final réellement persisté doit contenir LES DEUX réponses, pas
    // seulement la dernière à avoir écrit. C'est l'état final des données qui compte, pas
    // l'apparence d'un appel qui a « réussi ».
    const final = await getInspection(draft.client_uuid);
    expect(final).toBeDefined();
    expect(final?.items[answerA.item_template_id]).toEqual(answerA);
    expect(final?.items[answerB.item_template_id]).toEqual(answerB);
    expect(Object.keys(final?.items ?? {})).toHaveLength(2);
  });

  it("sérialise 10 écritures concurrentes sur le même brouillon sans en perdre une seule", async () => {
    const draft = makeLocalInspection();
    await putInspection(draft);

    const answers = Array.from({ length: 10 }, () => makeItemAnswer());
    await Promise.all(answers.map((a) => upsertItemAnswer(draft.client_uuid, a)));

    const final = await getInspection(draft.client_uuid);
    expect(Object.keys(final?.items ?? {})).toHaveLength(10);
    for (const answer of answers) {
      expect(final?.items[answer.item_template_id]).toEqual(answer);
    }
  });

  it("une écriture qui échoue (updater qui lève) ne bloque pas les écritures suivantes sur le même brouillon", async () => {
    const draft = makeLocalInspection();
    await putInspection(draft);

    const failing = updateInspection(draft.client_uuid, () => {
      throw new Error("erreur métier isolée");
    });
    await expect(failing).rejects.toThrow("erreur métier isolée");

    // La file ne doit pas rester bloquée : une écriture normale après l'échec doit passer.
    const answer = makeItemAnswer();
    const after = await upsertItemAnswer(draft.client_uuid, answer);
    expect(after.items[answer.item_template_id]).toEqual(answer);
  });
});
