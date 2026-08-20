import "@/lib/offline/__tests__/setupFakeIndexedDb";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Mock } from "vitest";
import { getAllPhotos, getInspection, getPhotosForInspection, putInspection, putPhoto } from "@/lib/offline/db";
import { requestSubmit, updateDraftFields, upsertItemAnswer } from "@/lib/offline/draft";
import { MAX_UPLOAD_ATTEMPTS, triggerSync } from "@/lib/offline/sync";
import {
  clearOfflineDb,
  deferred,
  makeInspectionResponse,
  makeItemAnswer,
  makeLocalInspection,
  makeLocalPhoto,
  makePhotoResponse,
} from "@/lib/offline/__tests__/fixtures";
import type { Inspection, Photo, RequiredAnglesResponse } from "@/lib/api/types";

vi.mock("@/lib/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/client")>("@/lib/api/client");
  return {
    ...actual,
    api: {
      get: vi.fn(),
      post: vi.fn(),
      patch: vi.fn(),
      put: vi.fn(),
      delete: vi.fn(),
      upload: vi.fn(),
    },
  };
});

// Import APRÈS le mock (même module, `vi.mock` est hissé par Vitest — l'import statique
// ci-dessus renvoie déjà la version mockée).
import { api, ApiError } from "@/lib/api/client";

const apiGet = api.get as unknown as Mock;
const apiPost = api.post as unknown as Mock;
const apiPatch = api.patch as unknown as Mock;
const apiPut = api.put as unknown as Mock;
const apiUpload = api.upload as unknown as Mock;

const REQUIRED_ANGLES_OK: RequiredAnglesResponse = {
  required_angles: ["face_avant"],
  captured_angles: [],
  missing_angles: ["face_avant"],
};

function networkError(): ApiError {
  return new ApiError(0, "internal_error", "Impossible de contacter le serveur.");
}

/**
 * Tests de concurrence RÉELS du moteur hors ligne (`lib/offline/sync.ts`), § mission de ce
 * jalon de tests : chaque scénario met en scène la course exacte décrite dans
 * implementation.md § J2 Frontend (« Points d'attention »), pas son apparence. L'assertion
 * porte sur L'ÉTAT FINAL DES DONNÉES (IndexedDB local + corps effectivement envoyé au
 * serveur mocké), jamais sur un simple drapeau booléen.
 */
describe("sync.ts — courses réseau réelles", () => {
  beforeEach(async () => {
    await clearOfflineDb();
    apiGet.mockReset();
    apiPost.mockReset();
    apiPatch.mockReset();
    apiPut.mockReset();
    apiUpload.mockReset();
    // Angles requis : par défaut un succès neutre, pour ne pas faire échouer les scénarios
    // qui ne testent pas spécifiquement cet appel.
    apiGet.mockResolvedValue(REQUIRED_ANGLES_OK);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it(
    "une réponse de checklist saisie PENDANT l'envoi réseau n'est ni perdue localement ni " +
      "considérée comme synchronisée à tort (repro bug 🔴 n°3, le plus grave des trois)",
    async () => {
      const draft = makeLocalInspection({ server_id: "srv-insp-1", items_dirty: false });
      const answer1 = makeItemAnswer();
      await putInspection({ ...draft, items: { [answer1.item_template_id]: answer1 }, items_dirty: true });

      const putItemsCall = deferred<Inspection>();
      apiPut.mockImplementation(() => putItemsCall.promise);

      // Démarre le tick — il va s'arrêter en plein `await api.put(.../items, ...)`.
      const tickPromise = triggerSync();

      // Laisse le micro-task queue avancer jusqu'à ce que `api.put` ait été appelé (capture
      // du corps envoyé), SANS résoudre encore la promesse réseau.
      await vi.waitFor(() => expect(apiPut).toHaveBeenCalledTimes(1));
      const sentBody = apiPut.mock.calls[0][1] as { items: unknown[] };
      // Le corps envoyé à CE tick ne doit contenir que ce qui existait au moment de la
      // relecture (juste avant l'appel réseau) — item2 n'existe pas encore.
      expect(sentBody.items).toHaveLength(1);

      // PENDANT que la requête réseau est encore en vol, le chauffeur coche une deuxième
      // réponse — c'est exactement la course décrite dans implementation.md.
      const answer2 = makeItemAnswer();
      await upsertItemAnswer(draft.client_uuid, answer2);

      // Le réseau finit par répondre avec succès à l'envoi qui ne contenait QUE answer1.
      putItemsCall.resolve(makeInspectionResponse({ id: draft.server_id! }));
      const result = await tickPromise;
      expect(result.status).toBe("ok");

      // 1) Rien n'est perdu LOCALEMENT : les deux réponses sont dans IndexedDB.
      const afterTick1 = await getInspection(draft.client_uuid);
      expect(Object.keys(afterTick1?.items ?? {})).toHaveLength(2);
      expect(afterTick1?.items[answer1.item_template_id]).toEqual(answer1);
      expect(afterTick1?.items[answer2.item_template_id]).toEqual(answer2);

      // 2) Le brouillon reste marqué « à synchroniser » : answer2 n'a jamais été envoyée,
      // donc `items_dirty` ne doit PAS être retombé à `false` — sinon plus aucune tentative
      // ultérieure ne la renverrait (c'est exactement le bug côté serveur constaté : items
      // manquants + `items_dirty=false`).
      expect(afterTick1?.items_dirty).toBe(true);

      // 3) Un second tick doit renvoyer l'état COMPLET (les deux réponses), et seulement
      // alors marquer la synchronisation comme faite.
      apiPut.mockReset();
      apiPut.mockResolvedValue(makeInspectionResponse({ id: draft.server_id! }));
      const secondTick = await triggerSync();
      expect(secondTick.status).toBe("ok");
      expect(apiPut).toHaveBeenCalledTimes(1);
      const secondBody = apiPut.mock.calls[0][1] as { items: unknown[] };
      expect(secondBody.items).toHaveLength(2);

      const afterTick2 = await getInspection(draft.client_uuid);
      expect(afterTick2?.items_dirty).toBe(false);
    },
  );

  it(
    "une modification de champ (kilométrage) PENDANT le PATCH réseau reste marquée à " +
      "synchroniser, jamais silencieusement écrasée (même course que les items, § fields_dirty)",
    async () => {
      const draft = makeLocalInspection({
        server_id: "srv-insp-2",
        fields_dirty: true,
        kilometrage_releve: 10000,
      });
      await putInspection(draft);

      const patchCall = deferred<void>();
      apiPatch.mockImplementation(() => patchCall.promise);

      const tickPromise = triggerSync();
      await vi.waitFor(() => expect(apiPatch).toHaveBeenCalledTimes(1));
      const sentBody = apiPatch.mock.calls[0][1] as { kilometrage_releve: number | null };
      expect(sentBody.kilometrage_releve).toBe(10000);

      // Le chauffeur corrige le kilométrage PENDANT que le PATCH précédent est encore en vol.
      await updateDraftFields(draft.client_uuid, { kilometrage_releve: 10042 });

      patchCall.resolve(undefined);
      await tickPromise;

      const afterTick1 = await getInspection(draft.client_uuid);
      // La valeur locale la plus récente doit être conservée...
      expect(afterTick1?.kilometrage_releve).toBe(10042);
      // ...et le brouillon doit rester marqué « à synchroniser » (10042 n'a jamais été
      // envoyé), sinon la correction resterait bloquée en local pour toujours.
      expect(afterTick1?.fields_dirty).toBe(true);

      apiPatch.mockReset();
      apiPatch.mockResolvedValue(undefined);
      await triggerSync();
      const secondBody = apiPatch.mock.calls[0][1] as { kilometrage_releve: number | null };
      expect(secondBody.kilometrage_releve).toBe(10042);
      const afterTick2 = await getInspection(draft.client_uuid);
      expect(afterTick2?.fields_dirty).toBe(false);
    },
  );

  it(
    "deux appels concurrents à triggerSync() ne déclenchent qu'UN SEUL tick réel " +
      "(sérialisation, pas de double envoi réseau)",
    async () => {
      const draft = makeLocalInspection({ server_id: "srv-insp-3", items_dirty: true });
      await putInspection({
        ...draft,
        items: { a: makeItemAnswer({ item_template_id: "a" }) },
      });

      const putItemsCall = deferred<Inspection>();
      apiPut.mockImplementation(() => putItemsCall.promise);

      const first = triggerSync();
      const second = triggerSync(); // arrive PENDANT que le premier est en vol.

      expect(second).toBe(first); // même promesse rendue, pas un second tick lancé en parallèle.

      putItemsCall.resolve(makeInspectionResponse({ id: draft.server_id! }));
      await Promise.all([first, second]);

      expect(apiPut).toHaveBeenCalledTimes(1); // pas de double envoi.
    },
  );

  it(
    "un besoin de synchronisation apparu PENDANT un tick en vol n'est pas perdu jusqu'au " +
      "prochain minuteur — il déclenche un tick de rattrapage immédiat (repro bug 🔴 n°2, " +
      "`rerunRequested`)",
    async () => {
      const draftA = makeLocalInspection({ server_id: "srv-insp-A", items_dirty: true });
      await putInspection({
        ...draftA,
        items: { a: makeItemAnswer({ item_template_id: "a" }) },
      });

      const putItemsCallA = deferred<Inspection>();
      apiPut.mockImplementation((path: string) => {
        if (path === `/inspections/${draftA.server_id}/items`) return putItemsCallA.promise;
        return Promise.resolve(makeInspectionResponse());
      });

      // Démarre le tick 1 — il va rester bloqué sur le PUT items du brouillon A.
      const running = triggerSync();
      await vi.waitFor(() => expect(apiPut).toHaveBeenCalledTimes(1));

      // PENDANT ce tick 1, un second brouillon devient synchronisable (nouvelle réponse de
      // checklist sur une AUTRE inspection, ou simplement un nouveau brouillon créé) — le
      // tick 1 ne le verra jamais, sa liste `pending` a déjà été figée au début du tick.
      const draftB = makeLocalInspection({ server_id: "srv-insp-B", items_dirty: true });
      await putInspection({
        ...draftB,
        items: { b: makeItemAnswer({ item_template_id: "b" }) },
      });

      // Un appelant (bouton « Réessayer », évènement `online`) redéclenche triggerSync()
      // pendant que le tick 1 tourne encore : sérialisé sur la même promesse, mais programme
      // un rattrapage.
      const duringTick1 = triggerSync();
      expect(duringTick1).toBe(running);

      putItemsCallA.resolve(makeInspectionResponse({ id: draftA.server_id! }));
      await running;

      // Sans appel manuel supplémentaire à triggerSync(), le rattrapage programmé par
      // `rerunRequested` doit traiter le brouillon B tout seul, immédiatement après la fin
      // du tick 1 — pas seulement au prochain minuteur de fond (20 s).
      await vi.waitFor(() => {
        const calledForB = apiPut.mock.calls.some(
          (call) => call[0] === `/inspections/${draftB.server_id}/items`,
        );
        expect(calledForB).toBe(true);
      });

      const finalB = await getInspection(draftB.client_uuid);
      expect(finalB?.items_dirty).toBe(false);
    },
  );

  it(
    "une soumission demandée PENDANT qu'un tick envoie encore les dernières photos n'est " +
      "jamais perdue : elle est traitée par le rattrapage immédiat, sans attendre le " +
      "minuteur de 20 s (repro bug 🔴 n°2, relecture fraîche de `pending_submit`)",
    async () => {
      const draft = makeLocalInspection({
        server_id: "srv-insp-4",
        // `items_dirty: true` (plutôt que tout à `false`) fait volontairement entrer ce
        // brouillon dans la liste `pending` du tick — sans ça, `needsSync()` l'ignorerait
        // purement à cause d'une photo en file (voir le test dédié « des photos mises en
        // file sans qu'aucun autre champ n'ait changé... » ci-dessus, qui isole CE problème
        // séparément). Ce test-ci porte sur la relecture fraîche de `pending_submit`, pas sur
        // le déclenchement du tick — l'isoler évite de faire dépendre cette assertion d'un
        // bug par ailleurs déjà documenté.
        items_dirty: true,
        fields_dirty: false,
        pending_submit: false,
        conclusion: "achat_direct",
        items: { a: makeItemAnswer({ item_template_id: "a" }) },
      });
      await putInspection(draft);
      const photo = makeLocalPhoto({
        inspection_client_uuid: draft.client_uuid,
        vehicle_id: draft.vehicle_id,
        upload_state: "queued",
      });
      await putPhoto(photo);

      apiPut.mockResolvedValue(makeInspectionResponse({ id: draft.server_id! })); // items : rapide, pas le point testé ici.
      const uploadCall = deferred<Photo>();
      apiUpload.mockImplementation(() => uploadCall.promise);
      apiPost.mockResolvedValue(makeInspectionResponse({ id: draft.server_id!, submitted_at: "2026-08-20T10:00:00Z" }));

      const running = triggerSync();
      await vi.waitFor(() => expect(apiUpload).toHaveBeenCalledTimes(1));

      // Le chauffeur clique « Achat direct » PENDANT que la dernière photo est encore en
      // cours d'envoi — `pending_submit` passe à `true` alors que le tick est déjà en vol.
      // `requestSubmit` pose AUSSI `fields_dirty: true` (draft.ts) : comme l'étape 2 (champs)
      // de CE tick est déjà passée au moment du clic, le brouillon ne peut pas être soumis
      // DANS ce même tick (l'étape 6 diffère volontairement la soumission tant que
      // `fields_dirty`/`items_dirty` ne sont pas retombés à `false`, § commentaire de
      // `sync.ts` étape 6) — ce n'est pas une perte, c'est le même appelant réel
      // (`useInspectionDraft.submit()`) qui rappelle `sync()` juste après avoir posé ces
      // drapeaux, exactement comme simulé ci-dessous.
      await requestSubmit(draft.client_uuid, "achat_direct");
      const duringTick = triggerSync(); // reproduit le `void sync()` de `useInspectionDraft.submit()`.
      expect(duringTick).toBe(running); // sérialisé sur le tick déjà en vol (mutex `tickInFlight`).

      uploadCall.resolve(makePhotoResponse());
      await running;

      // Le rattrapage `rerunRequested` doit soumettre IMMÉDIATEMENT après la fin du tick en
      // cours, sans attendre le minuteur de fond de 20 s — sans appel manuel supplémentaire à
      // `triggerSync()` ici.
      await vi.waitFor(() => {
        const submitCalls = apiPost.mock.calls.filter((call) => call[0] === `/inspections/${draft.server_id}/submit`);
        expect(submitCalls).toHaveLength(1);
      });

      await vi.waitFor(async () => {
        const final = await getInspection(draft.client_uuid);
        expect(final?.submitted_at).toBe("2026-08-20T10:00:00Z");
        expect(final?.pending_submit).toBe(false);
      });
    },
  );

  it(
    "un échec TRANSITOIRE (5xx passager) sur une photo au milieu d'un lot n'empêche pas les " +
      "autres de partir, et la photo en échec est rejouée sans jamais partir en double " +
      "(revue finale § 🟠 n°1 : 503, pas 409 — un 409/422 est désormais classé définitif, " +
      "voir le describe dédié plus bas)",
    async () => {
      // `items_dirty: true` force l'inclusion dans `pending` — isole la sémantique du LOT de
      // photos (ce que ce test vérifie) du bug 🔴 « needsSync ignore une photo seule »,
      // documenté séparément ci-dessous par son propre test dédié.
      const draft = makeLocalInspection({
        server_id: "srv-insp-5",
        items_dirty: true,
        items: { a: makeItemAnswer({ item_template_id: "a" }) },
      });
      await putInspection(draft);
      apiPut.mockResolvedValue(makeInspectionResponse({ id: draft.server_id! }));
      const p1 = makeLocalPhoto({ inspection_client_uuid: draft.client_uuid, angle: "face_avant" });
      const p2 = makeLocalPhoto({ inspection_client_uuid: draft.client_uuid, angle: "profil_gauche" });
      const p3 = makeLocalPhoto({ inspection_client_uuid: draft.client_uuid, angle: "profil_droit" });
      await putPhoto(p1);
      await putPhoto(p2);
      await putPhoto(p3);

      apiUpload.mockImplementation((_path: string, formData: FormData) => {
        const clientUuid = String(formData.get("client_uuid"));
        if (clientUuid === p2.client_uuid) {
          // 503 — panne serveur PASSAGÈRE, pas un conflit métier : `isDefinitivePhotoError`
          // (`sync.ts`) ne classe que 409/422 comme définitifs, ce statut reste retenté.
          return Promise.reject(new ApiError(503, "internal_error", "Service temporairement indisponible."));
        }
        return Promise.resolve(makePhotoResponse());
      });

      const result = await triggerSync();
      expect(result.photosSent).toBe(2);
      expect(result.photosFailed).toBe(1);

      const photosAfter = await getAllPhotos();
      const byId = Object.fromEntries(photosAfter.map((p) => [p.client_uuid, p]));
      expect(byId[p1.client_uuid].upload_state).toBe("sent");
      expect(byId[p2.client_uuid].upload_state).toBe("failed");
      expect(byId[p2.client_uuid].attempts).toBe(1);
      expect(byId[p3.client_uuid].upload_state).toBe("sent"); // p3 est bien partie malgré l'échec de p2.

      // Reprise : p2 réussit cette fois. p1/p3 ne doivent JAMAIS être renvoyées (déjà `sent`).
      // Note : `items_dirty` a été effacé par le tick précédent (PUT réussi) — sans un NOUVEL
      // évènement qui redirtye le brouillon, ce second appel à `triggerSync()` se heurterait
      // lui aussi au bug 🔴 (une photo `failed` seule ne redéclenche rien, cf. le test dédié
      // « corollaire » ci-dessous). On force ici cet évènement explicitement pour isoler LA
      // SÉMANTIQUE DE REPRISE elle-même (pas de doublon, retenter uniquement l'échec) de ce
      // bug déjà documenté séparément.
      await upsertItemAnswer(draft.client_uuid, makeItemAnswer({ item_template_id: "b" }));
      apiUpload.mockReset();
      apiUpload.mockResolvedValue(makePhotoResponse());
      const retryResult = await triggerSync();
      expect(retryResult.photosSent).toBe(1); // seule p2 était encore à envoyer.
      expect(apiUpload).toHaveBeenCalledTimes(1);
      const retryFormData = apiUpload.mock.calls[0][1] as FormData;
      expect(String(retryFormData.get("client_uuid"))).toBe(p2.client_uuid);

      const photosFinal = await getPhotosForInspection(draft.client_uuid);
      expect(photosFinal.every((p) => p.upload_state === "sent")).toBe(true);
      // Total d'appels réseau sur toute la séquence pour p1/p3 : un seul chacun (pas de doublon).
    },
  );

  it(
    "une coupure réseau AU MILIEU d'un lot de photos arrête le tick immédiatement : les " +
      "photos suivantes ne sont pas tentées (donc jamais envoyées en double au prochain tick)",
    async () => {
      // Même remarque que le test précédent : `items_dirty: true` isole la sémantique testée
      // ici (arrêt propre du LOT sur coupure réseau) du bug 🔴 documenté séparément.
      const draft = makeLocalInspection({
        server_id: "srv-insp-6",
        items_dirty: true,
        items: { a: makeItemAnswer({ item_template_id: "a" }) },
      });
      await putInspection(draft);
      apiPut.mockResolvedValue(makeInspectionResponse({ id: draft.server_id! }));
      const p1 = makeLocalPhoto({ inspection_client_uuid: draft.client_uuid, angle: "face_avant" });
      const p2 = makeLocalPhoto({ inspection_client_uuid: draft.client_uuid, angle: "profil_gauche" });
      const p3 = makeLocalPhoto({ inspection_client_uuid: draft.client_uuid, angle: "profil_droit" });
      await putPhoto(p1);
      await putPhoto(p2);
      await putPhoto(p3);

      apiUpload.mockImplementation((_path: string, formData: FormData) => {
        const clientUuid = String(formData.get("client_uuid"));
        if (clientUuid === p1.client_uuid) return Promise.resolve(makePhotoResponse());
        if (clientUuid === p2.client_uuid) return Promise.reject(networkError());
        // p3 ne devrait jamais être atteinte dans ce tick.
        return Promise.reject(new Error("p3 n'aurait jamais dû être tentée dans ce tick"));
      });

      const result = await triggerSync();
      expect(result.status).toBe("offline");
      expect(apiUpload).toHaveBeenCalledTimes(2); // p1 puis p2 — p3 jamais atteinte.

      const photosAfter = await getAllPhotos();
      const byId = Object.fromEntries(photosAfter.map((p) => [p.client_uuid, p]));
      expect(byId[p1.client_uuid].upload_state).toBe("sent");
      expect(byId[p2.client_uuid].upload_state).toBe("queued"); // remis en file, pas "failed".
      expect(byId[p3.client_uuid].upload_state).toBe("queued"); // jamais tentée.

      // Reprise réseau : p1 ne doit JAMAIS repartir (déjà envoyée), p2 et p3 doivent partir.
      // Même remarque que le test précédent : on force un nouvel évènement dirty pour isoler
      // la sémantique de reprise du bug 🔴 (déjà documenté séparément) plutôt que de la
      // redémontrer ici incidemment.
      await upsertItemAnswer(draft.client_uuid, makeItemAnswer({ item_template_id: "b" }));
      apiUpload.mockReset();
      apiUpload.mockResolvedValue(makePhotoResponse());
      const retry = await triggerSync();
      expect(retry.photosSent).toBe(2);
      expect(apiUpload).toHaveBeenCalledTimes(2);
      const sentUuids = apiUpload.mock.calls.map((call) => String((call[1] as FormData).get("client_uuid")));
      expect(sentUuids).not.toContain(p1.client_uuid);
      expect(sentUuids).toContain(p2.client_uuid);
      expect(sentUuids).toContain(p3.client_uuid);
    },
  );

  it(
    "un brouillon en attente au « démarrage » (rechargement de page) est repris et " +
      "synchronisé dès le premier tick, sans action supplémentaire",
    async () => {
      // Simule l'état IndexedDB tel qu'il serait retrouvé après un rechargement de page en
      // plein contrôle : un brouillon partiellement synchronisé + une photo encore en file.
      const draft = makeLocalInspection({
        server_id: "srv-insp-7",
        items_dirty: true,
      });
      await putInspection({
        ...draft,
        items: { a: makeItemAnswer({ item_template_id: "a" }) },
      });
      const photo = makeLocalPhoto({ inspection_client_uuid: draft.client_uuid, upload_state: "queued" });
      await putPhoto(photo);

      apiPut.mockResolvedValue(makeInspectionResponse({ id: draft.server_id! }));
      apiUpload.mockResolvedValue(makePhotoResponse());

      // Premier appel de `triggerSync()` après le « rechargement » (ex. montage de
      // `useOfflineSyncEngine` au chargement de l'app) — rien d'autre n'a préparé cet état.
      const result = await triggerSync();
      expect(result.status).toBe("ok");
      expect(result.photosSent).toBe(1);

      const finalInspection = await getInspection(draft.client_uuid);
      expect(finalInspection?.items_dirty).toBe(false);
      const finalPhotos = await getPhotosForInspection(draft.client_uuid);
      expect(finalPhotos[0].upload_state).toBe("sent");
    },
  );
});

/**
 * 🔴 BUG CONFIRMÉ (revue orchestrateur, `.agent-team/review-j2.md` § Bloquant n°1) —
 * `needsSync()` (`sync.ts:112-116`) ne retient un brouillon que si `!server_id`,
 * `fields_dirty`, `items_dirty` ou `pending_submit` : RIEN dans le cycle de vie d'une photo
 * (`draft.ts::enqueuePhoto`) ne pose l'un de ces drapeaux. Un brouillon déjà synchronisé
 * (checklist + champs déjà envoyés) auquel on ajoute des photos ne sera donc JAMAIS repris —
 * ni par l'évènement `online`, ni par le minuteur de 20 s, ni par le bouton « Réessayer » —
 * tant que le chauffeur n'a pas modifié un autre champ du brouillon.
 *
 * C'est très précisément le scénario réel : le chauffeur remplit son contrôle EN LIGNE, puis
 * descend au sous-sol et ne fait plus que photographier — le cas que `j2-terrain.spec.ts` ne
 * couvre pas puisqu'il remplit la checklist PENDANT la coupure, ce qui pose `items_dirty` et
 * sert d'amorce accidentelle au rejeu des photos (passager clandestin, pas une preuve du
 * critère d'acceptation « la reprise renvoie les photos en attente »).
 *
 * Ces deux tests sont ATTENDUS ROUGES tant que `needsSync` n'a pas été corrigé. Ils
 * constituent la preuve du bug avant correctif, et devront repasser au vert une fois
 * `needsSync` (ou `runSyncTick`) mis à jour pour tenir compte de `getAllPhotos()` — sans
 * modification de leur assertion.
 */
describe("sync.ts — 🔴 bug confirmé : la file de photos n'a aucun déclencheur de rejeu propre", () => {
  beforeEach(async () => {
    await clearOfflineDb();
    apiGet.mockReset();
    apiPost.mockReset();
    apiPatch.mockReset();
    apiPut.mockReset();
    apiUpload.mockReset();
    apiGet.mockResolvedValue(REQUIRED_ANGLES_OK);
  });

  it(
    "un brouillon DÉJÀ synchronisé (aucun champ ni item modifié) auquel on ajoute des photos " +
      "hors ligne ne les envoie jamais au retour du réseau — état final vérifié CÔTÉ SERVEUR " +
      "MOCKÉ, pas seulement un drapeau local",
    async () => {
      // Brouillon « propre » — exactement l'état après un premier tick de synchronisation
      // réussi (checklist + champs déjà envoyés, rien à renvoyer).
      const draft = makeLocalInspection({
        server_id: "srv-insp-clean",
        fields_dirty: false,
        items_dirty: false,
        pending_submit: false,
      });
      await putInspection(draft);

      // Le chauffeur prend 3 photos hors ligne puis le réseau revient — les 3 sont donc
      // `queued` (jamais tentées pendant la coupure), et le réseau EST DISPONIBLE pour ce
      // tick (le mock réussit systématiquement).
      const p1 = makeLocalPhoto({ inspection_client_uuid: draft.client_uuid, vehicle_id: draft.vehicle_id, angle: "face_avant" });
      const p2 = makeLocalPhoto({ inspection_client_uuid: draft.client_uuid, vehicle_id: draft.vehicle_id, angle: "profil_gauche" });
      const p3 = makeLocalPhoto({ inspection_client_uuid: draft.client_uuid, vehicle_id: draft.vehicle_id, angle: "profil_droit" });
      await putPhoto(p1);
      await putPhoto(p2);
      await putPhoto(p3);

      apiUpload.mockResolvedValue(makePhotoResponse());

      // Le retour du réseau, en pratique, déclenche `triggerSync()` (évènement `online`,
      // minuteur de 20 s, ou bouton « Réessayer » du bandeau — tous appellent la même
      // fonction). On l'appelle ici directement, ce qui est même GÉNÉREUX envers le code
      // testé (aucun bruit de minuteur/évènement DOM à simuler).
      const result = await triggerSync();

      // Preuve par l'état final, pas par un drapeau : les 3 photos doivent être arrivées
      // « chez le serveur » (le mock d'upload). Aujourd'hui, `result.status` vaut `"idle"`
      // et `apiUpload` n'est jamais appelé — c'est le bug.
      expect(result.status).toBe("ok");
      expect(result.photosSent).toBe(3);
      expect(apiUpload).toHaveBeenCalledTimes(3);

      const photosAfter = await getAllPhotos();
      expect(photosAfter.every((p) => p.upload_state === "sent")).toBe(true);
    },
  );

  it(
    "une photo passée en `failed` (ex. 401/413/500 passager) n'est jamais rejouée si le " +
      "brouillon reste par ailleurs « propre » — le bandeau ment en annonçant une nouvelle " +
      "tentative en cours (corollaire du même bug)",
    async () => {
      const draft = makeLocalInspection({
        server_id: "srv-insp-clean-2",
        fields_dirty: false,
        items_dirty: false,
        pending_submit: false,
      });
      await putInspection(draft);

      const failedPhoto = makeLocalPhoto({
        inspection_client_uuid: draft.client_uuid,
        vehicle_id: draft.vehicle_id,
        angle: "face_avant",
        upload_state: "failed",
        attempts: 1,
        error: "Erreur serveur passagère (500).",
      });
      await putPhoto(failedPhoto);

      // Le réseau est maintenant disponible et le serveur répondrait cette fois avec succès —
      // ENCORE FAUT-IL que le tick tente réellement de la rejouer.
      apiUpload.mockResolvedValue(makePhotoResponse());

      const result = await triggerSync();

      expect(result.status).toBe("ok");
      expect(result.photosSent).toBe(1);
      expect(apiUpload).toHaveBeenCalledTimes(1);

      const after = await getAllPhotos();
      expect(after[0].upload_state).toBe("sent");
    },
  );
});

/**
 * 🟠 Important (revue, § 2 et § 3) — dernières occurrences de la famille « lire avant `await`
 * réseau, écrire un instantané périmé après » : cette fois sur le store `photos`, qui n'a
 * aucun équivalent du mutex `updateInspection` de `db.ts`.
 */
describe("sync.ts — 🟠 courses restantes sur le store photos (revue § 2, § 3)", () => {
  beforeEach(async () => {
    await clearOfflineDb();
    apiGet.mockReset();
    apiPost.mockReset();
    apiPatch.mockReset();
    apiPut.mockReset();
    apiUpload.mockReset();
    apiGet.mockResolvedValue(REQUIRED_ANGLES_OK);
  });

  it(
    "🟠 repro § 2 — reprendre un angle (supprimer la photo non envoyée) PENDANT que son " +
      "upload est déjà en vol ressuscite l'enregistrement supprimé, verrouillant l'angle sur " +
      "la photo que le chauffeur voulait jeter",
    async () => {
      const draft = makeLocalInspection({ server_id: "srv-insp-race2", items_dirty: true, items: { a: makeItemAnswer({ item_template_id: "a" }) } });
      await putInspection(draft);
      apiPut.mockResolvedValue(makeInspectionResponse({ id: draft.server_id! }));

      const photo = makeLocalPhoto({
        inspection_client_uuid: draft.client_uuid,
        vehicle_id: draft.vehicle_id,
        angle: "face_avant",
        upload_state: "queued",
      });
      await putPhoto(photo);

      const uploadCall = deferred<Photo>();
      apiUpload.mockImplementation(() => uploadCall.promise);

      const running = triggerSync();
      await vi.waitFor(() => expect(apiUpload).toHaveBeenCalledTimes(1));

      // Pendant que l'upload est en vol, le chauffeur clique « Reprendre » sur cette même
      // photo — reproduit ici directement au niveau `db.ts`, comme le fait
      // `draft.ts::removeUnsentPhoto` (la garde y porte sur l'état déjà lu par l'UI, pas sur
      // une relecture fraîche — cf. revue § 2).
      const { deletePhoto } = await import("@/lib/offline/db");
      await deletePhoto(photo.client_uuid);

      const afterDelete = await getAllPhotos();
      expect(afterDelete).toHaveLength(0); // le chauffeur a bien vu la vignette disparaître.

      uploadCall.resolve(makePhotoResponse());
      await running;

      // Comportement attendu (pas encore garanti par le code) : la suppression du chauffeur
      // doit être respectée — l'enregistrement ne doit PAS être ressuscité par l'écriture
      // finale de `uploadOnePhoto`, qui capture un instantané d'avant la suppression.
      const afterTick = await getAllPhotos();
      expect(afterTick).toHaveLength(0);
    },
  );

  it(
    "🟠 repro § 3 — une photo capturée PENDANT la boucle d'upload du tick courant n'est pas " +
      "incluse dans ce tick (liste figée en tête de boucle) ; combiné au bug 🔴, elle n'a " +
      "alors aucun tick suivant pour la rattraper une fois seule en attente",
    async () => {
      const draft = makeLocalInspection({ server_id: "srv-insp-race3", items_dirty: true, items: { a: makeItemAnswer({ item_template_id: "a" }) } });
      await putInspection(draft);
      apiPut.mockResolvedValue(makeInspectionResponse({ id: draft.server_id! }));

      const p1 = makeLocalPhoto({ inspection_client_uuid: draft.client_uuid, vehicle_id: draft.vehicle_id, angle: "face_avant" });
      await putPhoto(p1);

      const uploadCall = deferred<Photo>();
      let uploadCallCount = 0;
      apiUpload.mockImplementation(() => {
        uploadCallCount += 1;
        return uploadCallCount === 1 ? uploadCall.promise : Promise.resolve(makePhotoResponse());
      });

      const running = triggerSync();
      await vi.waitFor(() => expect(apiUpload).toHaveBeenCalledTimes(1));

      // Rafale de capture : une deuxième photo est ajoutée PENDANT que la boucle d'upload du
      // tick courant est déjà en cours (cas explicitement cité par implementation.md § J2
      // Frontend).
      const p2 = makeLocalPhoto({ inspection_client_uuid: draft.client_uuid, vehicle_id: draft.vehicle_id, angle: "profil_gauche" });
      await putPhoto(p2);

      uploadCall.resolve(makePhotoResponse());
      await running;

      // p2 n'a pas pu partir DANS ce tick (comportement attendu, ce n'est pas le bug en soi).
      // Le point testé : un tick ULTÉRIEUR doit la rattraper — ce qui suppose que le
      // brouillon reste (ou redevienne) éligible à `needsSync`. Une fois le bug 🔴 corrigé
      // (needsSync tient compte des photos en file), ce test doit passer sans changement.
      apiUpload.mockReset();
      apiUpload.mockResolvedValue(makePhotoResponse());
      const nextTick = await triggerSync();
      expect(nextTick.photosSent).toBe(1);

      const finalPhotos = await getAllPhotos();
      expect(finalPhotos.every((p) => p.upload_state === "sent")).toBe(true);
    },
  );
});

/**
 * 🟠 Revue finale § n°1 — effet de bord direct du correctif du 🔴 : une photo en échec
 * redevenait éligible à CHAQUE tick, y compris pour un échec DÉFINITIF (409 « angle déjà
 * photographié », 422 de format invalide) qui ne peut par construction jamais changer d'issue
 * en renvoyant exactement le même octet. Conséquence prouvée par ces tests : sans distinction,
 * `attempts` était incrémenté sans jamais être lu, et `pending_submit` restait bloqué à `true`
 * pour toujours (`stillPendingPhotos` comptait `failed`) — le contrôle ne pouvait plus jamais
 * être soumis depuis l'appareil concerné.
 */
describe("sync.ts — 🟠 échec DÉFINITIF d'une photo (revue finale § n°1)", () => {
  beforeEach(async () => {
    await clearOfflineDb();
    apiGet.mockReset();
    apiPost.mockReset();
    apiPatch.mockReset();
    apiPut.mockReset();
    apiUpload.mockReset();
    apiGet.mockResolvedValue(REQUIRED_ANGLES_OK);
  });

  it.each([
    ["409", new ApiError(409, "conflict", "Cet angle a déjà été photographié.")],
    ["422", new ApiError(422, "validation_error", "Format de fichier invalide.")],
  ])(
    "un %s business (angle déjà pris / format invalide) passe DIRECTEMENT en " +
      "`failed_permanent` dès le premier échec — aucune tentative gâchée sur une erreur qui " +
      "ne peut pas changer d'issue",
    async (_label, error) => {
      const draft = makeLocalInspection({ server_id: "srv-insp-def-1", items_dirty: true, items: { a: makeItemAnswer({ item_template_id: "a" }) } });
      await putInspection(draft);
      apiPut.mockResolvedValue(makeInspectionResponse({ id: draft.server_id! }));
      const photo = makeLocalPhoto({ inspection_client_uuid: draft.client_uuid, vehicle_id: draft.vehicle_id, angle: "face_avant" });
      await putPhoto(photo);

      apiUpload.mockRejectedValue(error);

      const result = await triggerSync();
      expect(result.status).toBe("ok");
      expect(result.photosFailed).toBe(1);

      const after = await getAllPhotos();
      expect(after[0].upload_state).toBe("failed_permanent");
      expect(after[0].attempts).toBe(1); // une seule tentative, pas cinq.
    },
  );

  it(
    "une photo `failed_permanent` n'est plus JAMAIS rejouée automatiquement, même quand le " +
      "brouillon redevient dirty pour une autre raison",
    async () => {
      const draft = makeLocalInspection({ server_id: "srv-insp-def-2", items_dirty: true, items: { a: makeItemAnswer({ item_template_id: "a" }) } });
      await putInspection(draft);
      apiPut.mockResolvedValue(makeInspectionResponse({ id: draft.server_id! }));
      const photo = makeLocalPhoto({ inspection_client_uuid: draft.client_uuid, vehicle_id: draft.vehicle_id, angle: "face_avant" });
      await putPhoto(photo);
      apiUpload.mockRejectedValueOnce(new ApiError(409, "conflict", "Cet angle a déjà été photographié."));

      await triggerSync();
      const afterFirst = await getAllPhotos();
      expect(afterFirst[0].upload_state).toBe("failed_permanent");

      // Le brouillon redevient éligible pour une tout autre raison (nouvelle réponse de
      // checklist) — si `needsSync`/la boucle d'upload retenaient encore cette photo, elle
      // serait retentée ici.
      apiUpload.mockClear();
      apiUpload.mockRejectedValue(new Error("cette photo ne doit plus jamais être envoyée"));
      await upsertItemAnswer(draft.client_uuid, makeItemAnswer({ item_template_id: "b" }));
      const secondTick = await triggerSync();

      expect(apiUpload).not.toHaveBeenCalled();
      expect(secondTick.photosFailed).toBe(0);
      const afterSecond = await getAllPhotos();
      expect(afterSecond[0].upload_state).toBe("failed_permanent"); // état inchangé, pas retenté.
    },
  );

  it(
    "une photo `failed_permanent` ne bloque plus `pending_submit` à vie : la soumission est " +
      "tentée quand même, le serveur reste le seul juge de la complétude",
    async () => {
      const draft = makeLocalInspection({
        server_id: "srv-insp-def-3",
        fields_dirty: false,
        items_dirty: false,
        pending_submit: true,
        conclusion: "achat_direct",
        items: { a: makeItemAnswer({ item_template_id: "a" }) },
      });
      await putInspection(draft);
      const photo = makeLocalPhoto({
        inspection_client_uuid: draft.client_uuid,
        vehicle_id: draft.vehicle_id,
        angle: "face_avant",
        upload_state: "failed_permanent",
        attempts: 1,
        error: "Cet angle a déjà été photographié.",
      });
      await putPhoto(photo);

      apiPost.mockResolvedValue(makeInspectionResponse({ id: draft.server_id!, submitted_at: "2026-08-27T10:00:00Z" }));

      const result = await triggerSync();

      // Avant correctif : `stillPendingPhotos` comptait `failed_permanent`, la soumission
      // n'était JAMAIS tentée (`apiPost` jamais appelé, `pending_submit` bloqué à `true` pour
      // toujours). Preuve directe que ce n'est plus le cas.
      expect(apiPost).toHaveBeenCalledWith(`/inspections/${draft.server_id}/submit`, expect.anything());
      expect(result.inspectionsSubmitted).toBe(1);

      const after = await getInspection(draft.client_uuid);
      expect(after?.pending_submit).toBe(false);
      expect(after?.submitted_at).toBe("2026-08-27T10:00:00Z");
      // La photo en échec définitif reste telle quelle — ni renvoyée, ni maquillée en `sent`.
      const afterPhoto = (await getAllPhotos())[0];
      expect(afterPhoto.upload_state).toBe("failed_permanent");
    },
  );

  it(
    "un échec récurrent NON classé définitif (5xx passager persistant) bascule lui aussi en " +
      "`failed_permanent` après `MAX_UPLOAD_ATTEMPTS` tentatives — `attempts` sert enfin à " +
      "quelque chose, aucune photo ne boucle indéfiniment",
    async () => {
      const draft = makeLocalInspection({ server_id: "srv-insp-def-4", items_dirty: true, items: { a: makeItemAnswer({ item_template_id: "a" }) } });
      await putInspection(draft);
      apiPut.mockResolvedValue(makeInspectionResponse({ id: draft.server_id! }));
      const photo = makeLocalPhoto({ inspection_client_uuid: draft.client_uuid, vehicle_id: draft.vehicle_id, angle: "face_avant" });
      await putPhoto(photo);
      apiUpload.mockRejectedValue(new ApiError(503, "internal_error", "Service temporairement indisponible."));

      // `MAX_UPLOAD_ATTEMPTS` ticks — un besoin de resynchronisation posé avant chacun, sinon
      // `needsSync` ignorerait le brouillon dès que `items_dirty` retombe (comportement du 🔴
      // déjà corrigé, hors sujet ici : ce test isole le plafond de tentatives).
      for (let i = 0; i < MAX_UPLOAD_ATTEMPTS; i += 1) {
        await upsertItemAnswer(draft.client_uuid, makeItemAnswer({ item_template_id: `extra-${i}` }));
        await triggerSync();
      }

      const afterCap = await getAllPhotos();
      expect(afterCap[0].upload_state).toBe("failed_permanent");
      expect(afterCap[0].attempts).toBe(MAX_UPLOAD_ATTEMPTS);
      const callsAtCap = apiUpload.mock.calls.length;

      // Un tick de plus : la photo ne doit plus jamais être retentée.
      await upsertItemAnswer(draft.client_uuid, makeItemAnswer({ item_template_id: "one-more" }));
      await triggerSync();
      expect(apiUpload.mock.calls.length).toBe(callsAtCap); // aucun appel supplémentaire.
    },
  );
});
