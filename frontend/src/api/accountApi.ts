/* =========================================================
   ACCOUNT STATUS API

   Whether an account may still sign in.

   Only the exceptions are stored — a record exists here when
   somebody has been switched off, and no record means active.
   That keeps the map to a handful of entries however many
   citizens the platform grows to, and it means an account that
   has been reactivated returns to "no record" rather than
   carrying a stale flag around forever.

   Mock-backed for the same reason the rest of the pending
   endpoints are: the admin screen is the real product here,
   and the store behind it is one function away from being a
   FastAPI table.
   ========================================================= */

export type AccountStatus = "active" | "deactivated";

const STORAGE_KEY = "nyaymitra.accounts.status.v1";

type StatusMap = Record<string, AccountStatus>;

/* The chat/authority pattern: localStorage first, an in-memory
   copy behind it so a blocked quota degrades to "nothing is
   switched off" rather than silently reactivating everyone
   the admin just turned off. */
let memory: StatusMap | null = null;
let storageUsable = true;

function readAll(): StatusMap {
  if (storageUsable) {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);

      if (raw) {
        const parsed = JSON.parse(raw) as StatusMap;

        if (parsed && typeof parsed === "object") return parsed;
      }
    } catch {
      storageUsable = false;
    }
  }

  memory ??= {};
  return memory;
}

function writeAll(next: StatusMap): void {
  memory = next;

  if (!storageUsable) return;

  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    storageUsable = false;
  }
}

/** Anything without an explicit entry is active. */
export function getAccountStatus(userId: string): AccountStatus {
  const id = userId.trim();

  if (!id) return "active";

  return readAll()[id] ?? "active";
}

export function isDeactivated(userId: string): boolean {
  return getAccountStatus(userId) === "deactivated";
}

/**
 * Switch an account on or off.
 *
 * Reactivating clears the record rather than writing "active", so
 * the map only ever holds accounts that are actually off.
 */
export function setAccountStatus(
  userId: string,
  status: AccountStatus,
): void {
  const id = userId.trim();
  if (!id) return;

  const all = readAll();

  if (status === "active") {
    delete all[id];
  } else {
    all[id] = "deactivated";
  }

  writeAll(all);
}

/** Convenience for a toggle button that flips whatever is there. */
export function toggleAccountStatus(userId: string): AccountStatus {
  const next: AccountStatus = isDeactivated(userId) ? "active" : "deactivated";
  setAccountStatus(userId, next);
  return next;
}
