/* =========================================================
   STAFF WORK FIXTURES

   Stand-ins for the two staff endpoints that have not
   landed yet: the task queue and the document processing
   queue. Everything is keyed to a real CNR from cases.ts so
   these screens describe matters that actually exist on the
   Case Files screen, rather than inventing parallel ones.

   Both arrays are replaced wholesale once GET /api/tasks and
   GET /api/documents are available — the screens only ever
   read the exported types and these two constants.
   ========================================================= */

export interface StaffTask {
  id: string;
  title: string;
  cnr: string;
  due: string;
  priority: "High" | "Normal" | "Low";
  status: "Open" | "In progress" | "Done";
}

export interface StaffDocument {
  id: string;
  title: string;
  cnr: string;
  kind: "Court order" | "Written statement" | "Affidavit" | "Judgment";
  received: string;
  pages: number;
  pipeline: "Awaiting OCR" | "OCR complete" | "Translated" | "Filed";
}

export const STAFF_TASKS: StaffTask[] = [
  {
    id: "TASK_001",
    title: "File written statement before the next hearing",
    cnr: "PBASB00008022024",
    due: "2026-10-02",
    priority: "High",
    status: "In progress",
  },
  {
    id: "TASK_002",
    title: "Upload the adjourned cause list to the case file",
    cnr: "PBASA00010662024",
    due: "2026-10-09",
    priority: "Normal",
    status: "Open",
  },
  {
    id: "TASK_003",
    title: "Verify service of notice on the third respondent",
    cnr: "PBAS010001412024",
    due: "2026-09-30",
    priority: "High",
    status: "Open",
  },
  {
    id: "TASK_004",
    title: "Prepare the daily activity summary for the admin",
    cnr: "PBASB00009992025",
    due: "2026-10-01",
    priority: "Low",
    status: "Open",
  },
  {
    id: "TASK_005",
    title: "Reconcile hearing dates against the court's board",
    cnr: "PBASB00001112025",
    due: "2026-10-13",
    priority: "Normal",
    status: "Done",
  },
];

export const STAFF_DOCUMENTS: StaffDocument[] = [
  {
    id: "DOC_001",
    title: "Order sheet — adjournment on 14 Sep",
    cnr: "PBASB00008022024",
    kind: "Court order",
    received: "2026-09-14",
    pages: 3,
    pipeline: "Translated",
  },
  {
    id: "DOC_002",
    title: "Written statement of the respondent bank",
    cnr: "PBASA00010662024",
    kind: "Written statement",
    received: "2026-09-21",
    pages: 11,
    pipeline: "OCR complete",
  },
  {
    id: "DOC_003",
    title: "Affidavit of service",
    cnr: "PBAS010001412024",
    kind: "Affidavit",
    received: "2026-09-25",
    pages: 2,
    pipeline: "Awaiting OCR",
  },
  {
    id: "DOC_004",
    title: "Judgment on I.A. No. 4 of 2026",
    cnr: "PBASB00009992025",
    kind: "Judgment",
    received: "2026-09-08",
    pages: 18,
    pipeline: "Filed",
  },
  {
    id: "DOC_005",
    title: "Order directing replacement of the pump",
    cnr: "PBASB00001112025",
    kind: "Court order",
    received: "2026-09-18",
    pages: 4,
    pipeline: "Translated",
  },
];
