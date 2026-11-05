import { format, parseISO } from "date-fns";

/** "05 Nov 2026" for ISO dates / datetimes; em dash for empty. */
export function fmtDate(value: string | null | undefined): string {
  if (!value) return "—";
  return format(parseISO(value), "dd MMM yyyy");
}

export function fmtDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return format(parseISO(value), "dd MMM yyyy, HH:mm");
}

/** Date → "yyyy-MM-dd" for the API (local calendar date, no timezone shift). */
export function toIsoDate(d: Date | null): string | null {
  return d ? format(d, "yyyy-MM-dd") : null;
}

export function fromIsoDate(value: string | null | undefined): Date | null {
  return value ? parseISO(value) : null;
}
