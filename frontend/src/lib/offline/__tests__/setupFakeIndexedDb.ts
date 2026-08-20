import "fake-indexeddb/auto";

/**
 * `fake-indexeddb` délègue le clonage de ses enregistrements à `globalThis.structuredClone`
 * (aucune implémentation propre — cf. `node_modules/fake-indexeddb/build/{cjs,esm}/lib/
 * ObjectStore.js`). Sous jsdom, ce `structuredClone` existe mais ne sait pas cloner un `Blob`
 * niché dans un objet : la propriété redevient un objet générique dépouillé de son prototype
 * (`instanceof Blob` devient `false`), ce qui fait échouer
 * `new FormData().append("file", photo.blob, …)` dans `lib/offline/sync.ts` avec
 * `TypeError: parameter 2 is not of type 'Blob'` — bug documenté de jsdom
 * (https://github.com/jsdom/jsdom/issues/3363, référencé dans le README de fake-indexeddb,
 * § « jsdom »).
 *
 * Un vrai navigateur ne présente jamais ce problème (IndexedDB clone les `Blob` nativement,
 * y compris nichés dans un objet) — c'est un artefact de la double simulation jsdom +
 * fake-indexeddb, pas un comportement à reproduire dans le code applicatif. Le correctif
 * ci-dessous ne modifie que l'environnement de test : avant de déléguer au `structuredClone`
 * natif, chaque `Blob` trouvé (à n'importe quelle profondeur dans un objet/tableau simple) est
 * extrait et remplacé par un jeton, puis réinjecté TEL QUEL (identité conservée, pas de clonage
 * profond de ses octets) après le clonage natif du reste de la structure — suffisant pour des
 * tests unitaires en process unique, où aucune isolation mémoire entre « client » et « serveur
 * simulés » n'est requise.
 */
const nativeStructuredClone = globalThis.structuredClone;

// Clé « marqueur » en chaîne plutôt qu'un `Symbol` : le clonage structuré natif (l'algorithme
// que `nativeStructuredClone` implémente réellement, en aval de notre correctif) ignore par
// spécification les propriétés à clé `Symbol` — un marqueur en `Symbol` disparaîtrait donc
// pendant l'étape de clonage native, avant même d'atteindre `restoreBlobs`.
const BLOB_PLACEHOLDER_KEY = "__fakeIndexedDbBlobPlaceholder__";
interface BlobPlaceholder {
  [BLOB_PLACEHOLDER_KEY]: true;
  index: number;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && value.constructor === Object;
}

function isBlobPlaceholder(value: unknown): value is BlobPlaceholder {
  return isPlainObject(value) && value[BLOB_PLACEHOLDER_KEY] === true;
}

function extractBlobs(value: unknown, blobs: Blob[]): unknown {
  if (typeof Blob !== "undefined" && value instanceof Blob) {
    const index = blobs.length;
    blobs.push(value);
    const placeholder: BlobPlaceholder = { [BLOB_PLACEHOLDER_KEY]: true, index };
    return placeholder;
  }
  if (Array.isArray(value)) {
    return value.map((item) => extractBlobs(item, blobs));
  }
  if (isPlainObject(value)) {
    const result: Record<string, unknown> = {};
    for (const [key, v] of Object.entries(value)) {
      result[key] = extractBlobs(v, blobs);
    }
    return result;
  }
  return value;
}

function restoreBlobs(value: unknown, blobs: Blob[]): unknown {
  if (isBlobPlaceholder(value)) {
    return blobs[value.index];
  }
  if (Array.isArray(value)) {
    return value.map((item) => restoreBlobs(item, blobs));
  }
  if (isPlainObject(value)) {
    const result: Record<string, unknown> = {};
    for (const [key, v] of Object.entries(value)) {
      result[key] = restoreBlobs(v, blobs);
    }
    return result;
  }
  return value;
}

function blobAwareStructuredClone<T>(value: T, options?: StructuredSerializeOptions): T {
  const blobs: Blob[] = [];
  const sanitized = extractBlobs(value, blobs);
  const cloned = nativeStructuredClone(sanitized, options);
  return restoreBlobs(cloned, blobs) as T;
}

globalThis.structuredClone = blobAwareStructuredClone as typeof structuredClone;
