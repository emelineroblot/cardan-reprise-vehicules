"use client";

import { useState } from "react";
import Link from "next/link";
import { Bell } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { LoadingState } from "@/components/ui/loading-state";
import { EmptyState } from "@/components/ui/empty-state";
import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
  useUnreadNotificationCount,
} from "@/lib/api/hooks/useNotifications";
import { formatRelative } from "@/lib/format/date";
import type { Notification } from "@/lib/api/types";

function targetHref(notification: Notification): string | null {
  const payload = notification.payload as { vehicle_id?: string; mission_id?: string } | null;
  if (payload?.mission_id) return `/missions/${payload.mission_id}`;
  if (payload?.vehicle_id) return `/vehicules/${payload.vehicle_id}`;
  return null;
}

/**
 * Pastille + liste de notifications (brief J2 : « le chauffeur reçoit une notification à
 * l'affectation d'une mission »). Chemin nominal uniquement — persistées en base, jamais
 * dépendantes du web push réel (implementation.md § J2 Backend).
 */
export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const unreadCount = useUnreadNotificationCount();
  const notifications = useNotifications();
  const markRead = useMarkNotificationRead();
  const markAllRead = useMarkAllNotificationsRead();

  const count = unreadCount.data?.count ?? 0;

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="relative"
          aria-label={count > 0 ? `Notifications, ${count} non lue${count > 1 ? "s" : ""}` : "Notifications"}
        >
          <Bell className="size-4" aria-hidden="true" />
          {count > 0 ? (
            <span
              aria-hidden="true"
              className="absolute -right-0.5 -top-0.5 flex size-4 items-center justify-center rounded-full bg-destructive text-[10px] font-semibold text-destructive-foreground"
            >
              {count > 9 ? "9+" : count}
            </span>
          ) : null}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80 p-0">
        <div className="flex items-center justify-between border-b border-border px-3 py-2">
          <span className="text-sm font-medium">Notifications</span>
          {count > 0 ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => markAllRead.mutate()}
              disabled={markAllRead.isPending}
            >
              Tout marquer lu
            </Button>
          ) : null}
        </div>
        <div className="max-h-96 overflow-y-auto">
          {notifications.isLoading ? <LoadingState label="Chargement…" className="py-6" /> : null}
          {notifications.data && notifications.data.items.length === 0 ? (
            <EmptyState title="Aucune notification" className="border-0 py-8" />
          ) : null}
          <ul>
            {(notifications.data?.items ?? []).map((notification) => {
              const href = targetHref(notification);
              const content = (
                <div className="flex flex-col gap-0.5 px-3 py-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-medium text-foreground">{notification.titre}</p>
                    {!notification.read_at ? (
                      <span aria-hidden="true" className="mt-1 size-2 shrink-0 rounded-full bg-primary" />
                    ) : null}
                  </div>
                  <p className="text-sm text-muted-foreground">{notification.corps}</p>
                  <p className="text-xs text-muted-foreground">{formatRelative(notification.created_at)}</p>
                </div>
              );
              return (
                <li key={notification.id} className="border-b border-border last:border-0">
                  {href ? (
                    <Link
                      href={href}
                      className="block hover:bg-muted"
                      onClick={() => {
                        if (!notification.read_at) markRead.mutate(notification.id);
                        setOpen(false);
                      }}
                    >
                      {content}
                    </Link>
                  ) : (
                    <button
                      type="button"
                      className="block w-full text-left hover:bg-muted"
                      onClick={() => !notification.read_at && markRead.mutate(notification.id)}
                    >
                      {content}
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
