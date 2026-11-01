// Who this browser is to the backend. The API keeps runs per client: a reset drops only this
// client's runs, and `/runs` lists only them, so two visitors on one host never clobber each
// other. The id is random, kept in this browser, and means nothing anywhere else.

const KEY = "vandal.client";

let cached: string | null = null;

export function clientId(): string {
  if (cached) return cached;
  if (typeof window === "undefined") return "server";
  let id: string | null = null;
  try {
    id = window.localStorage.getItem(KEY);
  } catch {
    /* private mode */
  }
  if (!id) {
    id = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : Math.random().toString(36).slice(2) + Date.now().toString(36);
    try {
      window.localStorage.setItem(KEY, id);
    } catch {
      /* private mode: the id lives for this page load */
    }
  }
  cached = id;
  return id;
}
