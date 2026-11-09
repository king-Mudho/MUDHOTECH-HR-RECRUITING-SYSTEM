/**
 * Vacancy deadlines are entered in the vacancy's own timezone (EC-JOB-05) and stored as UTC.
 * `datetime-local` inputs give a wall-clock string ("2026-03-31T23:59"); these helpers convert
 * between that wall-clock time in an IANA zone and an ISO UTC instant, without a date library.
 */

function partsInZone(date: Date, timeZone: string): Record<string, number> {
  const fmt = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  const out: Record<string, number> = {};
  for (const p of fmt.formatToParts(date)) {
    if (p.type !== "literal") out[p.type] = Number(p.value);
  }
  return out;
}

/** Offset (ms) of `timeZone` from UTC at the given instant. */
function offsetAt(date: Date, timeZone: string): number {
  const p = partsInZone(date, timeZone);
  const asUtc = Date.UTC(p.year!, p.month! - 1, p.day!, p.hour!, p.minute!, p.second!);
  return asUtc - Math.floor(date.getTime() / 1000) * 1000;
}

/** "2026-03-31T23:59" in Africa/Harare -> "2026-03-31T21:59:00.000Z". */
export function zonedLocalToUtcIso(local: string, timeZone: string): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(local);
  if (!m) return null;
  const [, y, mo, d, h, mi] = m.map(Number) as [number, number, number, number, number, number];
  const guess = Date.UTC(y, mo - 1, d, h, mi);
  // Two passes handle DST transitions correctly for zones that observe them.
  let instant = guess - offsetAt(new Date(guess), timeZone);
  instant = guess - offsetAt(new Date(instant), timeZone);
  return new Date(instant).toISOString();
}

/** ISO UTC instant -> "YYYY-MM-DDTHH:mm" wall clock in `timeZone` (for datetime-local inputs). */
export function utcIsoToZonedLocal(iso: string | null | undefined, timeZone: string): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const p = partsInZone(date, timeZone);
  const pad = (n: number | undefined) => String(n ?? 0).padStart(2, "0");
  return `${p.year}-${pad(p.month)}-${pad(p.day)}T${pad(p.hour)}:${pad(p.minute)}`;
}

/** Human formatting of an instant in a zone, e.g. "31 Mar 2026, 23:59 (Africa/Harare)". */
export function formatInZone(
  iso: string | null | undefined,
  timeZone: string,
  locale = "en-GB",
): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const text = new Intl.DateTimeFormat(locale, {
    timeZone,
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(date);
  return `${text} (${timeZone})`;
}

export const COMMON_TIMEZONES = [
  "Africa/Harare",
  "Africa/Johannesburg",
  "Africa/Lusaka",
  "Africa/Gaborone",
  "Africa/Maputo",
  "Africa/Nairobi",
  "Africa/Lagos",
  "Europe/London",
  "UTC",
] as const;
