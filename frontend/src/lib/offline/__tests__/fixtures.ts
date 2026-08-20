import type { LocalInspection, LocalItemAnswer, LocalPhoto } from "@/lib/offline/types";
import type { Inspection, Photo } from "@/lib/api/types";

/**
 * Fabriques minimales pour les tests de concurrence du moteur hors ligne
 * (`db.mutex.test.ts`, `sync.concurrency.test.ts`). Volontairement en dehors de
 * `lib/offline/` de production : ce sont des données de test, jamais importées par le code
 * applicatif.
 */

let counter = 0;
function nextId(prefix: string): string {
  counter += 1;
  return `${prefix}-${counter}`;
}

export function makeLocalInspection(overrides: Partial<LocalInspection> = {}): LocalInspection {
  const now = new Date().toISOString();
  return {
    client_uuid: nextId("insp-client"),
    vehicle_id: nextId("vehicle"),
    mission_id: nextId("mission"),
    template_id: nextId("template"),
    started_at: now,
    kilometrage_releve: null,
    etat_general: null,
    conclusion: null,
    commentaire: null,
    items: {},
    server_id: null,
    required_angles: null,
    fields_dirty: false,
    items_dirty: false,
    pending_submit: false,
    submitted_at: null,
    last_sync_error: null,
    missing_items: null,
    missing_angles: null,
    updated_at: now,
    ...overrides,
  };
}

export function makeItemAnswer(overrides: Partial<LocalItemAnswer> = {}): LocalItemAnswer {
  return {
    item_template_id: nextId("item-template"),
    valeur_bool: true,
    valeur_note: null,
    valeur_texte: null,
    valeur_num: null,
    commentaire: null,
    ...overrides,
  };
}

export function makeLocalPhoto(overrides: Partial<LocalPhoto> = {}): LocalPhoto {
  return {
    client_uuid: nextId("photo-client"),
    inspection_client_uuid: nextId("insp-client"),
    vehicle_id: nextId("vehicle"),
    angle: "face_avant",
    phase: "controle",
    blob: new Blob(["photo"], { type: "image/jpeg" }),
    content_type: "image/jpeg",
    byte_size: 5,
    width: 1600,
    height: 1200,
    checksum_sha256: "0".repeat(64),
    captured_at: new Date().toISOString(),
    upload_state: "queued",
    attempts: 0,
    error: null,
    server_id: null,
    server_url: null,
    ...overrides,
  };
}

/** Réponse serveur minimale pour `POST /inspections` / `POST .../submit` — seuls les champs
 * réellement lus par `sync.ts` sont renseignés, le reste est casté (fixture de test, pas un
 * contrat public). */
export function makeInspectionResponse(overrides: Partial<Inspection> = {}): Inspection {
  return {
    id: nextId("insp-server"),
    submitted_at: null,
    ...overrides,
  } as unknown as Inspection;
}

/** Réponse serveur minimale pour `POST /vehicles/{id}/photos`. */
export function makePhotoResponse(overrides: Partial<Photo> = {}): Photo {
  return {
    id: nextId("photo-server"),
    url: "/api/backend/v1/photos/file/runtime/x.jpg",
    ...overrides,
  } as unknown as Photo;
}

/** Une promesse contrôlable de l'extérieur — pour orchestrer précisément une course entre
 * un appel réseau simulé et une mutation locale, sans jamais dépendre d'un `sleep`. */
export interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (error: unknown) => void;
}

export function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/**
 * Vide les trois stores IndexedDB du module hors ligne — `lib/offline/db.ts` n'expose aucune
 * fonction de remise à zéro (aucun appelant applicatif n'en a besoin), et `fake-indexeddb`
 * persiste ses données pour toute la durée du fichier de test (le module `db.ts` n'est chargé
 * qu'une fois, son `dbPromise` mis en cache survit d'un test à l'autre) — sans ce nettoyage,
 * `getAllInspections()`/`getAllPhotos()` renvoient un mélange de TOUS les tests précédents du
 * même fichier. Ouvre sa propre connexion en passant par l'API IndexedDB brute plutôt que par
 * `db.ts` (pas de fonction `clear` exportée), sur la même base (`cardan-terrain`, version 1) :
 * IndexedDB autorise plusieurs connexions concurrentes à la même base, visibles l'une de
 * l'autre.
 */
const OFFLINE_DB_STORES = ["inspections", "photos", "checklist_cache"] as const;

export async function clearOfflineDb(): Promise<void> {
  const db = await new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open("cardan-terrain", 1);
    // Si ce test est le tout premier du fichier à ouvrir la base, `db.ts` ne l'a pas encore
    // créée : sans ce handler, l'ouverture réussirait sur une base VIDE (aucun store), et le
    // `transaction(storeName, ...)` ci-dessous échouerait avec `NotFoundError`. Réplique donc
    // ici la même création de stores que `db.ts::openDb` — un `onupgradeneeded` ultérieur
    // (déclenché par `db.ts` en second) serait un no-op puisque `contains` les verrait déjà.
    request.onupgradeneeded = () => {
      const created = request.result;
      for (const storeName of OFFLINE_DB_STORES) {
        if (!created.objectStoreNames.contains(storeName)) {
          const keyPath = storeName === "checklist_cache" ? "template_id" : "client_uuid";
          created.createObjectStore(storeName, { keyPath });
        }
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Ouverture IndexedDB refusée."));
  });
  await Promise.all(
    OFFLINE_DB_STORES.map(
      (storeName) =>
        new Promise<void>((resolve, reject) => {
          const tx = db.transaction(storeName, "readwrite");
          tx.objectStore(storeName).clear();
          tx.oncomplete = () => resolve();
          tx.onerror = () => reject(tx.error ?? new Error("Vidage IndexedDB refusé."));
        }),
    ),
  );
  db.close();
}
