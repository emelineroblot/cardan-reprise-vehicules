"use client";

import { useState } from "react";
import { Bell, BellRing } from "lucide-react";
import { Button } from "@/components/ui/button";
import { usePushPublicKey, useCreatePushSubscription } from "@/lib/api/hooks/usePushSubscription";

function urlBase64ToUint8Array(base64: string): BufferSource {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const base64Safe = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64Safe);
  const bytes = Uint8Array.from([...raw].map((char) => char.charCodeAt(0)));
  return bytes.buffer as ArrayBuffer;
}

/**
 * Abonnement web push RÉEL — n'existe et ne s'affiche que si
 * `GET /notifications/push-public-key` répond `enabled: true` (clés VAPID configurées
 * côté serveur). Le point de vérité est cet appel runtime, jamais une variable
 * d'environnement front dupliquée (implementation.md § J2 Backend). Le chemin nominal
 * (pastille + liste de `NotificationBell`) ne dépend d'aucune ligne de ce fichier.
 */
export function PushSubscribeButton() {
  const publicKey = usePushPublicKey();
  const subscribe = useCreatePushSubscription();
  const [state, setState] = useState<"idle" | "subscribed" | "denied" | "error">("idle");

  if (!publicKey.data?.enabled || !publicKey.data.public_key) return null;
  if (typeof window === "undefined" || !("serviceWorker" in navigator) || !("PushManager" in window)) return null;

  const handleSubscribe = async () => {
    try {
      const registration = await navigator.serviceWorker.ready;
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setState("denied");
        return;
      }
      const pushSubscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey.data!.public_key as string),
      });
      const json = pushSubscription.toJSON();
      await subscribe.mutateAsync({
        endpoint: json.endpoint as string,
        p256dh: json.keys?.p256dh as string,
        auth: json.keys?.auth as string,
        user_agent: navigator.userAgent,
      });
      setState("subscribed");
    } catch (error) {
      console.warn("Abonnement push impossible — la pastille de notification reste fonctionnelle.", error);
      setState("error");
    }
  };

  if (state === "subscribed") {
    return (
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <BellRing className="size-4" aria-hidden="true" />
        Notifications push activées sur cet appareil.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      <Button type="button" variant="outline" size="sm" onClick={handleSubscribe} disabled={subscribe.isPending}>
        <Bell className="size-4" aria-hidden="true" />
        Activer les notifications sur cet appareil
      </Button>
      {state === "denied" ? (
        <p className="text-xs text-muted-foreground">
          Autorisation refusée par le navigateur — modifiable dans ses réglages de site.
        </p>
      ) : null}
      {state === "error" ? (
        <p className="text-xs text-muted-foreground">Abonnement indisponible pour l&apos;instant.</p>
      ) : null}
    </div>
  );
}
