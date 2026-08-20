/**
 * Dates — l'API renvoie des dates `date` ISO (métier) et des horodatages
 * `timestamptz` ISO-8601 UTC (plan.md § 3.5). Le formatage en heure locale est
 * une affaire de front : tout vit ici.
 */

const DATE_FORMATTER = new Intl.DateTimeFormat("fr-FR", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

const DATETIME_FORMATTER = new Intl.DateTimeFormat("fr-FR", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

const RELATIVE_FORMATTER = new Intl.RelativeTimeFormat("fr-FR", { numeric: "auto" });

/** Formate une date ISO (`2026-08-20`) en `20/08/2026`. `null`/invalide → « — ». */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso.length <= 10 ? `${iso}T00:00:00` : iso);
  if (Number.isNaN(date.getTime())) return "—";
  return DATE_FORMATTER.format(date);
}

/** Formate un horodatage ISO en `20/08/2026 14:32`. `null`/invalide → « — ». */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return DATETIME_FORMATTER.format(date);
}

/** Formate un horodatage en durée relative courte (« il y a 4 min »). */
export function formatRelative(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  const diffMs = date.getTime() - now.getTime();
  const diffMinutes = Math.round(diffMs / 60_000);
  if (Math.abs(diffMinutes) < 60) {
    return RELATIVE_FORMATTER.format(diffMinutes, "minute");
  }
  const diffHours = Math.round(diffMinutes / 60);
  if (Math.abs(diffHours) < 24) {
    return RELATIVE_FORMATTER.format(diffHours, "hour");
  }
  const diffDays = Math.round(diffHours / 24);
  return RELATIVE_FORMATTER.format(diffDays, "day");
}

/** Convertit une `Date` locale en chaîne `date` ISO (`YYYY-MM-DD`) sans dérive de fuseau. */
export function toDateInputValue(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/**
 * Convertit la valeur d'un `<input type="datetime-local">` (heure locale, sans offset) en
 * horodatage ISO-8601 **avec** offset — le backend compare `payload.rdv_at` à
 * `datetime.now(UTC)` (`state_machine.py::_guard_rdv_futur`), une chaîne locale nue serait
 * mal interprétée. `null` si vide ou invalide (jamais une exception).
 */
export function datetimeLocalToIso(value: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString();
}

/**
 * Horodatage local `YYYY-MM-DDTHH:mm` utilisable comme `min` d'un
 * `<input type="datetime-local">` — une minute d'avance par défaut pour laisser le temps de
 * valider avant que « maintenant » ne dépasse la valeur saisie.
 */
export function minDatetimeLocalValue(marginMs = 60_000): string {
  const date = new Date(Date.now() + marginMs);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
