/* =========================================================
   NYAYMITRA — CASE DOCUMENT STORE

   One store serves three screens that would otherwise each
   invent their own: the citizen's case detail (documents they
   uploaded when filing), the court-orders screen (the orders
   themselves, grouped by case), and the lawyer's caseload
   (the same file, seen from the other side).

   Files are kept in the browser, so the practical limit is
   the localStorage quota. Metadata is always stored; the
   bytes are kept as a data URL only while the file is small
   enough to leave room for the rest. A document too large to
   hold still appears, still lists its name, size and date —
   it simply cannot be previewed, and says so rather than
   silently vanishing.
   ========================================================= */

export type DocumentCategory =
  | "Filing"
  | "Evidence"
  | "Identity"
  | "Court order"
  | "Correspondence"
  | "Other";

export const DOCUMENT_CATEGORIES: DocumentCategory[] = [
  "Filing",
  "Evidence",
  "Identity",
  "Court order",
  "Correspondence",
  "Other",
];

export interface CaseDocument {
  id: string;

  /* Owning matter. Everything is grouped by this rather than
     by folder — a document has no existence outside a case. */
  cnr: string;

  /* Account that uploaded it, so the viewer can tell whose
     copy this is when the lawyer opens the same matter. */
  owner_user_id: string;

  name: string;
  mime: string;
  size: number;
  category: DocumentCategory;

  uploadedAt: string;

  /* Base64 data URL, or null when the file was too large to
     keep. Never a blob URL — those die with the tab. */
  dataUrl: string | null;

  /* Set when dataUrl is null, so the UI can explain the gap. */
  note?: string;
}

/* ~1 MB. Large enough for a scanned page or a short order,
   small enough that four or five uploads do not exhaust the
   quota and knock the whole store over to memory-only. */
const PREVIEW_LIMIT = 1_000_000;

const STORAGE_KEY = "nyaymitra.documents.v1";

let memory: CaseDocument[] | null = null;
let storageUsable = true;

function read(): CaseDocument[] {
  if (storageUsable) {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);

      if (raw) {
        const parsed = JSON.parse(raw) as unknown;

        if (Array.isArray(parsed))
          return parsed as CaseDocument[];
      }
    } catch {
      storageUsable = false;
    }
  }

  memory ??= [];
  return memory;
}

function write(next: CaseDocument[]): void {
  memory = next;

  if (!storageUsable) return;

  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    /* Quota. Metadata already made it into `memory`, so the
       list still renders; only persistence is lost. */
    storageUsable = false;
  }
}

/* =========================================================
   READING A FILE
   ========================================================= */

/**
 * Resolves to a data URL, or null if the browser refuses —
 * an unreadable file, a huge one, or a tab with no access to
 * storage at all. Callers treat null as "keep the metadata".
 */
export function readFileAsDataUrl(
  file: File,
): Promise<string | null> {
  if (file.size > PREVIEW_LIMIT) return Promise.resolve(null);

  return new Promise((resolve) => {
    const reader = new FileReader();

    reader.onload = () =>
      resolve(
        typeof reader.result === "string"
          ? reader.result
          : null,
      );
    reader.onerror = () => resolve(null);
    reader.readAsDataURL(file);
  });
}

/* =========================================================
   QUERIES
   ========================================================= */

export function listDocuments(cnr: string): CaseDocument[] {
  return read()
    .filter((doc) => doc.cnr === cnr)
    .sort((a, b) => b.uploadedAt.localeCompare(a.uploadedAt));
}

/** Court orders only, across every case — the court-orders
 *  screen needs one flat list grouped by matter. */
export function listCourtOrders(
  ownerUserId: string,
): CaseDocument[] {
  return read()
    .filter(
      (doc) =>
        doc.owner_user_id === ownerUserId &&
        doc.category === "Court order",
    )
    .sort((a, b) => b.uploadedAt.localeCompare(a.uploadedAt));
}

export function countDocuments(cnr: string): number {
  return read().filter((doc) => doc.cnr === cnr).length;
}

/* =========================================================
   WRITING
   ========================================================= */

export type NewDocumentInput = {
  cnr: string;
  owner_user_id: string;
  category: DocumentCategory;
  file: File;
  dataUrl: string | null;
};

export function addDocument(
  input: NewDocumentInput,
): CaseDocument {
  const document: CaseDocument = {
    id: `doc_${Date.now().toString(36)}_${Math.random()
      .toString(36)
      .slice(2, 8)}`,
    cnr: input.cnr,
    owner_user_id: input.owner_user_id,
    name: input.file.name,
    mime: input.file.type || "application/octet-stream",
    size: input.file.size,
    category: input.category,
    uploadedAt: new Date().toISOString(),
    dataUrl: input.dataUrl,
    ...(input.dataUrl === null && {
      note: "Stored as a record only — this browser could not keep the file itself, so there is nothing to preview.",
    }),
  };

  write([document, ...read()]);

  return document;
}

/** Removes one document. The list re-reads after calling it. */
export function removeDocument(id: string): void {
  write(read().filter((doc) => doc.id !== id));
}

/** Removes every document belonging to one matter. Used when a
 *  case is discarded before it is ever filed. */
export function removeDocumentsFor(cnr: string): void {
  write(read().filter((doc) => doc.cnr !== cnr));
}
