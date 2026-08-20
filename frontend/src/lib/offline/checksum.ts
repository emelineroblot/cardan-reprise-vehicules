/**
 * `sha256` hexadécimal d'un `Blob` — recalculé et comparé côté serveur
 * (`app/services/photos.py`, implementation.md § J2 Backend) : une photo tronquée par une
 * coupure réseau en cours d'upload doit être détectée, pas stockée silencieusement.
 * `crypto.subtle` exige un contexte sécurisé (HTTPS ou `localhost`), déjà garanti par le
 * périmètre PWA (l'accès caméra l'exige de toute façon).
 */
export async function sha256Hex(blob: Blob): Promise<string> {
  const buffer = await blob.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}
