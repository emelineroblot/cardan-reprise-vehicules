"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import {
  computeAngleProgress,
  enqueuePhoto,
  getOrCreateDraft,
  removeUnsentPhoto,
  requestSubmit,
  updateDraftFields,
  upsertItemAnswer,
  type AngleProgress,
  type DraftFieldsPatch,
} from "@/lib/offline/draft";
import { getActiveInspectionForVehicle, getInspection, getPhotosForInspection } from "@/lib/offline/db";
import { triggerSync } from "@/lib/offline/sync";
import type { LocalInspection, LocalItemAnswer, LocalPhoto } from "@/lib/offline/types";
import type { ChecklistTemplateBrief, InspectionConclusion, PhotoAngle, PhotoPhase } from "@/lib/api/types";

const RELOAD_INTERVAL_MS = 1_500;

/**
 * Brouillon local d'inspection (décision C) : lit/crée l'IndexedDB local, jamais un appel
 * réseau direct pour le rendu — c'est le rôle de `lib/offline/sync.ts`, invoqué en tâche
 * de fond après chaque écriture locale.
 *
 * État en `useState` + rechargement explicite/polling, PAS TanStack Query : cette donnée
 * est un état d'APPAREIL local (IndexedDB), pas un cache de réponse serveur — TanStack
 * Query est fait pour le second cas (c'est le choix retenu ailleurs dans l'app, plan.md
 * § 4 décision H) et son modèle d'invalidation par clé s'est avéré peu fiable ici en
 * conditions réelles (rafale de captures rapprochées) : un rechargement direct depuis
 * IndexedDB, déclenché après chaque écriture ET sondé en secours, est plus simple à
 * garantir correct pour cet usage précis.
 */
export function useInspectionDraft(vehicleId: string, missionId: string) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<LocalInspection | undefined>(undefined);
  const [photos, setPhotos] = useState<LocalPhoto[]>([]);
  const [angleProgress, setAngleProgress] = useState<AngleProgress | undefined>(undefined);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  // Écriture locale d'une photo refusée (revue J2 § 6 — cas réel : quota IndexedDB
  // dépassé, `QuotaExceededError`) : distinct de `error` ci-dessus (qui invalide tout
  // l'écran de contrôle) — ici, seule la dernière capture a échoué, le reste du contrôle
  // reste utilisable. Le chauffeur DOIT le savoir immédiatement : sans ça, la vignette ne
  // s'affiche simplement jamais et il croit avoir raté sa photo, la reprend en boucle,
  // pendant qu'elle n'a jamais existé nulle part (ni en local, ni côté serveur).
  const [photoError, setPhotoError] = useState<string | null>(null);

  // Référence stable vers le brouillon courant, lue par les callbacks sans les recréer à
  // chaque changement d'état (évite un aller-retour de dépendances useCallback/useEffect).
  const draftRef = useRef<LocalInspection | undefined>(undefined);

  // File d'écriture (mutex) : `updateDraftFields`/`upsertItemAnswer`/`requestSubmit`
  // font chacune un lire-modifier-écrire sur LE MÊME enregistrement (`draft.items` est un
  // objet fusionné). Deux réponses de checklist cochées coup sur coup (chauffeur rapide, ou
  // tout appelant qui n'attend pas la fin d'un appel avant le suivant) peuvent chevaucher
  // leur lecture — la seconde écrase alors la première avec une version d'`items` non à
  // jour. Constaté en conditions réelles : plusieurs réponses obligatoires perdues sans
  // erreur visible. Toute mutation du brouillon passe donc par cette file strictement
  // séquentielle, quel que soit l'ordre d'appel.
  const writeQueueRef = useRef<Promise<unknown>>(Promise.resolve());
  const enqueueWrite = useCallback(<T,>(fn: () => Promise<T>): Promise<T> => {
    const result = writeQueueRef.current.then(fn, fn);
    writeQueueRef.current = result.catch(() => undefined);
    return result;
  }, []);

  const reload = useCallback(async () => {
    const current = draftRef.current;
    if (!current) return;
    // Recharge PAR CLEF (`getInspection`), pas `getActiveInspectionForVehicle` : ce
    // dernier ne filtre plus les brouillons soumis depuis le correctif J2 (review §5)
    // — mais il redérive « le plus récent brouillon de ce véhicule » depuis `getAll()`
    // à chaque appel, une requête plus large et plus coûteuse pour recharger un
    // enregistrement dont on connaît déjà la clé. `getInspection` va droit à
    // l'enregistrement courant, sans repasser par ce filtrage/tri.
    const [freshDraft, freshPhotos] = await Promise.all([
      getInspection(current.client_uuid),
      getPhotosForInspection(current.client_uuid),
    ]);
    const effectiveDraft = freshDraft ?? current;
    draftRef.current = effectiveDraft;
    setDraft(effectiveDraft);
    setPhotos(freshPhotos);
    setAngleProgress(await computeAngleProgress(effectiveDraft));
  }, []);

  const sync = useCallback(async () => {
    const result = await triggerSync(queryClient);
    await reload();
    return result;
  }, [queryClient, reload]);

  // Bootstrap : récupère le brouillon actif ou en crée un — une seule fois par
  // (vehicleId, missionId).
  useEffect(() => {
    if (!vehicleId || !missionId) return;
    let cancelled = false;

    (async () => {
      setIsLoading(true);
      setError(null);
      try {
        let current = await getActiveInspectionForVehicle(vehicleId);
        if (!current) {
          const templates = await queryClient.fetchQuery<ChecklistTemplateBrief[]>({
            queryKey: ["checklist-templates"],
            queryFn: () => api.get<ChecklistTemplateBrief[]>("/checklist-templates?is_active=true"),
          });
          const templateId = templates[0]?.id;
          if (!templateId) {
            throw new Error(
              "Aucun référentiel de contrôle actif n'a pu être chargé — une connexion est nécessaire pour démarrer un nouveau contrôle.",
            );
          }
          current = await getOrCreateDraft(vehicleId, missionId, templateId);
        }
        if (cancelled) return;
        draftRef.current = current;
        setDraft(current);
        const [initialPhotos, initialProgress] = await Promise.all([
          getPhotosForInspection(current.client_uuid),
          computeAngleProgress(current),
        ]);
        if (cancelled) return;
        setPhotos(initialPhotos);
        setAngleProgress(initialProgress);
        setIsLoading(false);
        // Tentative immédiate, non bloquante : au moment où le contrôle démarre, le réseau
        // vient très probablement d'être utilisé (transition véhicule qui a amené ici).
        void sync();
      } catch (err) {
        if (!cancelled) {
          setError(err);
          setIsLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `sync`/`queryClient` sont stables (identité fixée par leurs propres deps), seuls vehicleId/missionId doivent redéclencher le bootstrap.
  }, [vehicleId, missionId]);

  // Sondage de secours (décision C) : une lecture IndexedDB locale est quasi gratuite,
  // absorbe toute rafale de captures rapprochées sans dépendre uniquement du timing d'un
  // rechargement explicite après chaque mutation.
  useEffect(() => {
    const interval = window.setInterval(() => void reload(), RELOAD_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [reload]);

  const setFields = useCallback(
    async (patch: DraftFieldsPatch) => {
      if (!draftRef.current) return;
      const clientUuid = draftRef.current.client_uuid;
      await enqueueWrite(() => updateDraftFields(clientUuid, patch));
      await reload();
      void sync();
    },
    [enqueueWrite, reload, sync],
  );

  const setItemAnswer = useCallback(
    async (answer: LocalItemAnswer) => {
      if (!draftRef.current) return;
      const clientUuid = draftRef.current.client_uuid;
      await enqueueWrite(() => upsertItemAnswer(clientUuid, answer));
      await reload();
      void sync();
    },
    [enqueueWrite, reload, sync],
  );

  const addPhoto = useCallback(
    async (file: File, angle: PhotoAngle, phase: PhotoPhase = "controle") => {
      if (!draftRef.current) return;
      try {
        await enqueuePhoto(draftRef.current.client_uuid, draftRef.current.vehicle_id, file, angle, phase);
      } catch (err) {
        // Échec d'écriture locale (revue J2 § 6) : la photo n'existe nulle part — ni en
        // local, ni côté serveur. Jamais un rejet silencieux (`PhotoAngleGrid` n'attend pas
        // cette promesse, un rejet non géré ici serait invisible à l'écran).
        setPhotoError(
          err instanceof DOMException && err.name === "QuotaExceededError"
            ? "Stockage de l'appareil plein — cette photo n'a pas pu être enregistrée. Libérez de l'espace puis reprenez cet angle."
            : "Cette photo n'a pas pu être enregistrée sur l'appareil — reprenez cet angle.",
        );
        return;
      }
      setPhotoError(null);
      await reload();
      void sync();
    },
    [reload, sync],
  );

  const retakePhoto = useCallback(
    async (photo: LocalPhoto) => {
      try {
        await removeUnsentPhoto(photo);
      } catch (err) {
        // 🟡 Correctif revue finale § n°5 : `removeUnsentPhoto` lève désormais sur
        // `"already_sent"` (la photo est passée `sent`/`uploading` entre le rendu de la
        // vignette — rafraîchie toutes les 1,5 s — et le clic sur « Reprendre »). Avant ce
        // correctif, le rejet n'était géré nulle part : une résurrection silencieuse avait
        // simplement été remplacée par un échec silencieux. Réutilise `photoError`, déjà
        // affiché à l'écran pour `addPhoto`.
        setPhotoError(err instanceof Error ? err.message : "Cette photo n'a pas pu être retirée — réessayez dans un instant.");
        await reload();
        return;
      }
      setPhotoError(null);
      await reload();
    },
    [reload],
  );

  const submit = useCallback(
    async (conclusion: InspectionConclusion) => {
      if (!draftRef.current) return;
      const clientUuid = draftRef.current.client_uuid;
      await enqueueWrite(() => requestSubmit(clientUuid, conclusion));
      await reload();
      void sync();
    },
    [enqueueWrite, reload, sync],
  );

  const pendingPhotoCount = useMemo(
    () => photos.filter((p) => p.upload_state === "queued" || p.upload_state === "uploading").length,
    [photos],
  );
  // Échecs transitoires ET définitifs comptent tous les deux comme « ont besoin d'attention »
  // — `failed_permanent` (revue finale § 🟠 n°1) n'est pas un sous-cas de `failed`, mais reste
  // à signaler au même titre.
  const failedPhotoCount = useMemo(
    () => photos.filter((p) => p.upload_state === "failed" || p.upload_state === "failed_permanent").length,
    [photos],
  );

  return {
    draft,
    isLoading,
    error,
    photoError,
    dismissPhotoError: useCallback(() => setPhotoError(null), []),
    photos,
    pendingPhotoCount,
    failedPhotoCount,
    angleProgress,
    setFields,
    setItemAnswer,
    addPhoto,
    retakePhoto,
    submit,
    sync,
    refresh: reload,
  };
}
