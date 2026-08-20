import type { CachedChecklistTemplate, LocalInspection, LocalPhoto } from "@/lib/offline/types";
import type { ChecklistTemplate } from "@/lib/api/types";

/**
 * Wrapper IndexedDB minimal, sans dépendance externe (décision C, plan.md § 4 : « il faut
 * une file et un worker de rejeu », posé volontairement à la main plutôt que via une
 * librairie tierce non auditée pour ce jalon — le besoin réel tient en trois stores et une
 * dizaine d'opérations). Aucune fonction ici ne lève au-delà de son propre store : un
 * navigateur sans IndexedDB (mode privé strict de certains navigateurs) dégrade
 * silencieusement vers « rien n'est persisté localement », jamais un crash de l'écran de
 * contrôle.
 */
const DB_NAME = "cardan-terrain";
const DB_VERSION = 1;

export const STORE_INSPECTIONS = "inspections";
export const STORE_PHOTOS = "photos";
export const STORE_CHECKLIST_CACHE = "checklist_cache";

let dbPromise: Promise<IDBDatabase> | null = null;

function openDb(): Promise<IDBDatabase> {
  if (typeof indexedDB === "undefined") {
    return Promise.reject(new Error("IndexedDB indisponible dans cet environnement."));
  }
  if (!dbPromise) {
    dbPromise = new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains(STORE_INSPECTIONS)) {
          db.createObjectStore(STORE_INSPECTIONS, { keyPath: "client_uuid" });
        }
        if (!db.objectStoreNames.contains(STORE_PHOTOS)) {
          db.createObjectStore(STORE_PHOTOS, { keyPath: "client_uuid" });
        }
        if (!db.objectStoreNames.contains(STORE_CHECKLIST_CACHE)) {
          db.createObjectStore(STORE_CHECKLIST_CACHE, { keyPath: "template_id" });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error ?? new Error("Ouverture IndexedDB refusée."));
    });
  }
  return dbPromise;
}

async function withStore<T>(
  storeName: string,
  mode: IDBTransactionMode,
  fn: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  const db = await openDb();
  return new Promise<T>((resolve, reject) => {
    const tx = db.transaction(storeName, mode);
    const store = tx.objectStore(storeName);
    const result = fn(store);
    result.onsuccess = () => resolve(result.result);
    result.onerror = () => reject(result.error ?? new Error("Opération IndexedDB refusée."));
    tx.onerror = () => reject(tx.error ?? new Error("Transaction IndexedDB refusée."));
  });
}

// --- Inspections ------------------------------------------------------------

export async function putInspection(inspection: LocalInspection): Promise<void> {
  await withStore(STORE_INSPECTIONS, "readwrite", (store) => store.put(inspection));
}

export async function getInspection(clientUuid: string): Promise<LocalInspection | undefined> {
  return withStore(STORE_INSPECTIONS, "readonly", (store) => store.get(clientUuid));
}

/**
 * Lecture-modification-écriture ATOMIQUE d'un brouillon — dans UNE SEULE transaction
 * IndexedDB `readwrite`, jamais une lecture puis une écriture séparées.
 *
 * C'est ce qui protège contre les courses locales, y compris ENTRE ONGLETS. IndexedDB
 * garantit qu'aucune autre transaction `readwrite` de portée chevauchante ne peut s'exécuter
 * tant que celle-ci n'est pas terminée, quelle que soit la connexion qui l'a ouverte — donc y
 * compris depuis un AUTRE onglet, qui a sa propre instance de ce module (donc son propre
 * `dbPromise`) mais partage la MÊME base IndexedDB sous-jacente. Un premier essai avec un
 * verrou tenu en mémoire de module (`Map` de promesses) ne protégeait que les écritures DANS
 * le même onglet — repro `db.multi-tab.test.ts` : deux « onglets » (deux instances de module
 * séparées, `vi.resetModules()`) qui écrivent chacun sur le même brouillon perdaient une des
 * deux réponses, l'un des deux verrous en mémoire ignorant totalement l'autre. En confiant
 * l'atomicité à la transaction IndexedDB elle-même (partagée par construction, contrairement
 * à un `Map` JS), le même code protège les deux cas sans distinction.
 *
 * Deux réponses de checklist tapées coup sur coup, ou une réponse tapée pendant qu'un tick de
 * synchronisation écrit le résultat d'un appel réseau précédent (même onglet ou non), partent
 * donc chacune d'une lecture fraîche DANS la transaction, jamais d'une copie en mémoire
 * capturée avant un `await` réseau.
 */
export async function updateInspection(
  clientUuid: string,
  updater: (current: LocalInspection) => LocalInspection,
): Promise<LocalInspection> {
  const db = await openDb();
  return new Promise<LocalInspection>((resolve, reject) => {
    const tx = db.transaction(STORE_INSPECTIONS, "readwrite");
    const store = tx.objectStore(STORE_INSPECTIONS);
    let updated: LocalInspection | undefined;

    const getRequest = store.get(clientUuid);
    getRequest.onsuccess = () => {
      const current = getRequest.result as LocalInspection | undefined;
      if (!current) {
        reject(new Error(`Brouillon local introuvable (${clientUuid}).`));
        return;
      }
      try {
        updated = updater(current);
      } catch (error) {
        // Erreur métier de l'appelant (ex. validation) : rejeter SANS écrire, mais laisser
        // la transaction se terminer normalement (rien ne l'empêche, aucune requête en
        // vol) — chaque appel ouvre sa propre transaction, un échec ici ne bloque donc
        // aucun appel suivant sur ce même brouillon.
        reject(error);
        return;
      }
      const putRequest = store.put(updated);
      putRequest.onerror = () => reject(putRequest.error ?? new Error("Écriture IndexedDB refusée."));
    };
    getRequest.onerror = () => reject(getRequest.error ?? new Error("Lecture IndexedDB refusée."));

    tx.oncomplete = () => {
      if (updated) resolve(updated);
      // Sinon : la transaction s'est terminée sans écriture (brouillon introuvable, ou
      // `updater` en échec) — déjà rejetée ci-dessus.
    };
    tx.onerror = () => reject(tx.error ?? new Error("Transaction IndexedDB refusée."));
  });
}

export async function getAllInspections(): Promise<LocalInspection[]> {
  return withStore(STORE_INSPECTIONS, "readonly", (store) => store.getAll());
}

/**
 * Le brouillon local le plus récent d'un véhicule, **soumis ou non** — utilisé au bootstrap
 * (`lib/offline/draft.ts::getOrCreateDraft`) pour retrouver le contrôle en cours plutôt que
 * d'en recréer un.
 *
 * Filtrer sur `!submitted_at` ici (comme avant) créait une seconde inspection serveur à
 * chaque rechargement de page juste après soumission (revue J2 § 5) : le véhicule reste en
 * `CONTROLE_EN_COURS` tant que la transition suivante n'a pas eu lieu, donc les deux
 * préconditions du backend restaient réunies, et le brouillon fraîchement soumis sortait de
 * son propre filtre — invisible au bootstrap, un second brouillon (nouveau `client_uuid`)
 * était créé à sa place, écran vierge au lieu du récapitulatif. La page affiche déjà le bon
 * état (`alreadySubmitted`, `controle/page.tsx`) une fois qu'elle reçoit un brouillon soumis :
 * il suffisait de ne plus le lui cacher.
 *
 * Filtré en mémoire depuis `getAll()` plutôt que via un index IndexedDB dédié : le volume est
 * de toute façon dérisoire (quelques brouillons par navigateur).
 */
export async function getActiveInspectionForVehicle(vehicleId: string): Promise<LocalInspection | undefined> {
  const all = await getAllInspections();
  const candidates = all.filter((i) => i.vehicle_id === vehicleId);
  candidates.sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime());
  return candidates[0];
}

// --- Photos -------------------------------------------------------------

export async function putPhoto(photo: LocalPhoto): Promise<void> {
  await withStore(STORE_PHOTOS, "readwrite", (store) => store.put(photo));
}

export async function getPhoto(clientUuid: string): Promise<LocalPhoto | undefined> {
  return withStore(STORE_PHOTOS, "readonly", (store) => store.get(clientUuid));
}

export async function deletePhoto(clientUuid: string): Promise<void> {
  await withStore(STORE_PHOTOS, "readwrite", (store) => store.delete(clientUuid));
}

/**
 * Même principe que `updateInspection` ci-dessus, appliqué au store `photos` (revue J2 § 2) :
 * ce store n'avait aucun équivalent du mutex des inspections — `sync.ts::uploadOnePhoto`
 * écrivait un instantané capturé AVANT l'appel réseau, ressuscitant après coup une photo que
 * le chauffeur avait supprimée entre-temps (« Reprendre l'angle » pendant que l'envoi était
 * déjà en vol). Relit l'état frais DANS la transaction juste avant d'écrire ; si
 * l'enregistrement a disparu, n'écrit rien et ne le ressuscite jamais — renvoie `undefined`
 * plutôt que de (re)créer silencieusement une entrée que l'utilisateur a choisi de jeter.
 */
export async function updatePhoto(
  clientUuid: string,
  updater: (current: LocalPhoto) => LocalPhoto,
): Promise<LocalPhoto | undefined> {
  const db = await openDb();
  return new Promise<LocalPhoto | undefined>((resolve, reject) => {
    const tx = db.transaction(STORE_PHOTOS, "readwrite");
    const store = tx.objectStore(STORE_PHOTOS);
    let updated: LocalPhoto | undefined;
    let found = false;

    const getRequest = store.get(clientUuid);
    getRequest.onsuccess = () => {
      const current = getRequest.result as LocalPhoto | undefined;
      if (!current) return; // Supprimée entre-temps : rien à écrire, `tx.oncomplete` renverra `undefined`.
      try {
        updated = updater(current);
      } catch (error) {
        reject(error);
        return;
      }
      found = true;
      const putRequest = store.put(updated);
      putRequest.onerror = () => reject(putRequest.error ?? new Error("Écriture IndexedDB refusée."));
    };
    getRequest.onerror = () => reject(getRequest.error ?? new Error("Lecture IndexedDB refusée."));

    tx.oncomplete = () => resolve(found ? updated : undefined);
    tx.onerror = () => reject(tx.error ?? new Error("Transaction IndexedDB refusée."));
  });
}

export type RemoveUnsentPhotoOutcome = "deleted" | "not_found" | "already_sent";

/**
 * Retire une photo non envoyée en relisant l'état frais DANS la transaction, jamais l'objet
 * React périmé passé par l'appelant (revue J2 § 2 : l'écran ne se rafraîchit que toutes les
 * 1,5 s — `useInspectionDraft.ts::RELOAD_INTERVAL_MS` — le bouton « Reprendre » peut donc
 * rester visible sur une photo déjà en cours d'envoi côté réseau).
 */
export async function deleteUnsentPhoto(clientUuid: string): Promise<RemoveUnsentPhotoOutcome> {
  const db = await openDb();
  return new Promise<RemoveUnsentPhotoOutcome>((resolve, reject) => {
    const tx = db.transaction(STORE_PHOTOS, "readwrite");
    const store = tx.objectStore(STORE_PHOTOS);
    let outcome: RemoveUnsentPhotoOutcome = "not_found";

    const getRequest = store.get(clientUuid);
    getRequest.onsuccess = () => {
      const current = getRequest.result as LocalPhoto | undefined;
      if (!current) return; // outcome reste "not_found".
      if (current.upload_state === "sent" || current.upload_state === "uploading") {
        outcome = "already_sent";
        return;
      }
      const deleteRequest = store.delete(clientUuid);
      deleteRequest.onerror = () => reject(deleteRequest.error ?? new Error("Suppression IndexedDB refusée."));
      outcome = "deleted";
    };
    getRequest.onerror = () => reject(getRequest.error ?? new Error("Lecture IndexedDB refusée."));

    tx.oncomplete = () => resolve(outcome);
    tx.onerror = () => reject(tx.error ?? new Error("Transaction IndexedDB refusée."));
  });
}

/** Filtré en mémoire depuis `getAll()`, même arbitrage que `getActiveInspectionForVehicle`
 * ci-dessus (plafond de 30 photos/véhicule, § 4 décision C : le volume ne justifie pas un
 * index dédié). */
export async function getPhotosForInspection(inspectionClientUuid: string): Promise<LocalPhoto[]> {
  const all = await getAllPhotos();
  return all.filter((p) => p.inspection_client_uuid === inspectionClientUuid);
}

export async function getAllPhotos(): Promise<LocalPhoto[]> {
  return withStore(STORE_PHOTOS, "readonly", (store) => store.getAll());
}

/**
 * Purge les photos déjà envoyées d'un brouillon (revue J2 § 6) : appelée une fois la
 * soumission confirmée côté serveur (`sync.ts`, étape 6). Le blob compressé (200 à 400 Ko)
 * n'a plus aucune raison d'occuper le quota IndexedDB une fois l'octet en sécurité côté
 * serveur — `removeUnsentPhoto`/`deleteUnsentPhoto` refusent déjà de toucher une photo
 * `sent` tant que le brouillon est en cours, mais rien ne les retirait après coup, véhicule
 * après véhicule. Aucune UI ne relit ces photos après soumission (le récapitulatif n'affiche
 * plus `PhotoAngleGrid`, `controle/page.tsx`).
 */
export async function deleteSentPhotosForInspection(inspectionClientUuid: string): Promise<void> {
  const all = await getPhotosForInspection(inspectionClientUuid);
  const sentIds = all.filter((p) => p.upload_state === "sent").map((p) => p.client_uuid);
  if (sentIds.length === 0) return;

  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE_PHOTOS, "readwrite");
    const store = tx.objectStore(STORE_PHOTOS);
    for (const id of sentIds) store.delete(id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error ?? new Error("Purge IndexedDB refusée."));
  });
}

// --- Cache checklist ------------------------------------------------------

export async function putCachedChecklistTemplate(template: ChecklistTemplate): Promise<void> {
  const entry: CachedChecklistTemplate = {
    template_id: template.id,
    template,
    cached_at: new Date().toISOString(),
  };
  await withStore(STORE_CHECKLIST_CACHE, "readwrite", (store) => store.put(entry));
}

export async function getCachedChecklistTemplate(templateId: string): Promise<ChecklistTemplate | undefined> {
  const entry = await withStore<CachedChecklistTemplate | undefined>(STORE_CHECKLIST_CACHE, "readonly", (store) =>
    store.get(templateId),
  );
  return entry?.template;
}
