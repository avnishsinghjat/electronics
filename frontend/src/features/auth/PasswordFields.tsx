import { z } from "zod";

export const MIN_PASSWORD = 10;

/** Mirrors the server policy so users see problems before submitting. */
export function passwordSchema(username: string | undefined) {
  return z
    .string()
    .min(MIN_PASSWORD, `At least ${MIN_PASSWORD} characters`)
    .refine((v) => !/^\d+$/.test(v) && !/^[A-Za-z]+$/.test(v), "Mix letters with digits or symbols")
    .refine((v) => !username || !v.toLowerCase().includes(username.toLowerCase()), "Must not contain your username");
}
