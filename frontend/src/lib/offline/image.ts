/**
 * Compression côté client (décision C, plan.md § 4) : `createImageBitmap` + `canvas`,
 * côté long ramené à 1600 px, JPEG qualité 0,75 — avant l'écriture dans IndexedDB, sinon
 * le quota du navigateur explose sur un contrôle de 12+ photos.
 */
const MAX_SIDE = 1600;
const JPEG_QUALITY = 0.75;

/** Dimensions cible en conservant le ratio — fonction pure, testable indépendamment du
 * pipeline `canvas` (non disponible en environnement de test jsdom). */
export function computeTargetDimensions(
  width: number,
  height: number,
  maxSide = MAX_SIDE,
): { width: number; height: number } {
  if (width <= 0 || height <= 0) return { width: 0, height: 0 };
  if (width <= maxSide && height <= maxSide) return { width, height };
  const scale = width >= height ? maxSide / width : maxSide / height;
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
  };
}

export interface CompressedImage {
  blob: Blob;
  width: number;
  height: number;
}

/**
 * Compresse un fichier image capturé par l'appareil. Dégrade sur le fichier d'origine
 * (jamais d'exception non gérée qui bloquerait la capture) si `createImageBitmap`/`canvas`
 * sont indisponibles — cas résiduel sur d'anciens navigateurs, journalisé mais non
 * bloquant : une photo non compressée reste une photo valide.
 */
export async function compressImage(file: File | Blob): Promise<CompressedImage> {
  try {
    if (typeof createImageBitmap !== "function") {
      throw new Error("createImageBitmap indisponible");
    }
    const bitmap = await createImageBitmap(file);
    const { width, height } = computeTargetDimensions(bitmap.width, bitmap.height);
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Contexte canvas 2D indisponible");
    ctx.drawImage(bitmap, 0, 0, width, height);
    bitmap.close?.();

    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY),
    );
    if (!blob) throw new Error("Échec d'encodage JPEG");
    return { blob, width, height };
  } catch (error) {
    console.warn("Compression image indisponible, envoi du fichier d'origine.", error);
    const dimensions = await readImageDimensions(file);
    return { blob: file, ...dimensions };
  }
}

function readImageDimensions(file: File | Blob): Promise<{ width: number; height: number }> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve({ width: img.naturalWidth, height: img.naturalHeight });
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      // Dernier repli : dimensions inconnues plutôt qu'une exception qui bloquerait la
      // capture — le backend exige `width`/`height` en entiers positifs (`422` sinon), 1×1
      // reste une valeur techniquement valide pour ne pas perdre la photo.
      resolve({ width: 1, height: 1 });
    };
    img.src = url;
  });
}
