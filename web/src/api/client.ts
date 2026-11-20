import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export type Schema = components["schemas"];
export const api = createClient<paths>({ baseUrl: "/api/v1" });

let csrfToken = "";
export const setCsrf = (t: string) => {
  csrfToken = t;
};
export const csrfHeader = () => ({ "X-CSRF-Token": csrfToken });

export class Unauthenticated extends Error {}

/** Unwrap an openapi-fetch result; a 401 becomes `Unauthenticated`, and the app shows the sign-in screen. */
export async function unwrap<T>(
  p: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await p;
  if (response.status === 401) {
    throw new Unauthenticated("Authentication required");
  }
  if (error !== undefined || data === undefined) {
    const e = error as { detail?: string; title?: string } | undefined;
    throw new Error(e?.detail ?? e?.title ?? `Request failed (${response.status})`);
  }
  return data;
}
