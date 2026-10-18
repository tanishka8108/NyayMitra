/* =========================================================
   ADMIN VERIFICATION API

   The Admin Dashboard's rulings travel here: /api/admin/* is
   ADMIN-only, every call carries the signed-in session's
   bearer token, and `verification_status` changes nowhere
   else in the frontend — no local copy, no optimistic word
   the server has not stored.

   Two vocabularies meet at this boundary. The database
   speaks PENDING / APPROVED / REJECTED (the CHECK constraint
   in database/auth_schema.sql); the dashboard's pills and
   buttons speak Pending / Verified / Rejected, the words the
   rest of the app already show. The mapping lives here and
   only here, so nothing half-translated leaks into a screen.

   The real endpoints are covered by
   NyayMitra-feature-lawyer-api/tests/test_verification_admin.py
   and test_lawyer_documents.py.
   ========================================================= */

import { apiRequest, LAWYER_API_BASE_URL } from "./config";
import { loadSession } from "../auth/session";

/* The server's vocabulary — exactly as stored. */
export type VerificationStatus = "PENDING" | "APPROVED" | "REJECTED";

/* The dashboard's vocabulary — what the pills say. */
export type VerificationLabel = "Pending" | "Verified" | "Rejected";

export interface AdminDocument {
  filename: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  uploaded_at: string | null;
}

export interface AdminLawyer {
  lawyer_id: string;
  user_id: number;
  full_name: string;
  email: string;
  license_id: string;
  practice_areas: string[];
  verification_status: VerificationStatus;
  verified_by: number | null;
  verified_at: string | null;
  created_at: string | null;
  is_demo: boolean;
  bar_council: string | null;
  years_of_experience: number | null;
  professional_phone_number: string | null;
  professional_bio: string | null;
  document: AdminDocument | null;
}

export interface AdminLawyerListResponse {
  count: number;
  total_count: number;
  page: number;
  limit: number;
  total_pages: number;
  lawyers: AdminLawyer[];
}

const LABEL_BY_STATUS: Record<VerificationStatus, VerificationLabel> = {
  APPROVED: "Verified",
  PENDING: "Pending",
  REJECTED: "Rejected",
};

const STATUS_BY_LABEL: Record<VerificationLabel, VerificationStatus> = {
  Verified: "APPROVED",
  Pending: "PENDING",
  Rejected: "REJECTED",
};

/** APPROVED -> "Verified", and so on. */
export function toLabel(status: VerificationStatus): VerificationLabel {
  return LABEL_BY_STATUS[status];
}

/** "Verified" -> APPROVED, and so on. */
export function toStatus(label: VerificationLabel): VerificationStatus {
  return STATUS_BY_LABEL[label];
}

export async function getAdminLawyers(
  params: {
    status?: VerificationStatus;
    page?: number;
    limit?: number;
  } = {},
): Promise<AdminLawyerListResponse> {
  const query = new URLSearchParams();

  if (params.status) query.set("status", params.status);
  if (params.page !== undefined) query.set("page", String(params.page));
  if (params.limit !== undefined) query.set("limit", String(params.limit));

  const queryString = query.toString();

  return apiRequest<AdminLawyerListResponse>(
    LAWYER_API_BASE_URL,
    `/api/admin/lawyers${queryString ? `?${queryString}` : ""}`,
  );
}

export function getAdminLawyer(lawyerId: string): Promise<AdminLawyer> {
  return apiRequest<AdminLawyer>(
    LAWYER_API_BASE_URL,
    `/api/admin/lawyers/${encodeURIComponent(lawyerId.trim())}`,
  );
}

export function setAdminVerification(
  lawyerId: string,
  status: VerificationStatus,
): Promise<AdminLawyer> {
  return apiRequest<AdminLawyer>(
    LAWYER_API_BASE_URL,
    `/api/admin/lawyers/${encodeURIComponent(lawyerId.trim())}`,
    {
      method: "PATCH",
      body: JSON.stringify({ verification_status: status }),
    },
  );
}

export async function fetchVerificationDocument(
  lawyerId: string,
): Promise<Blob> {
  /*
   * Not apiRequest: the answer is bytes, not JSON — and the
   * bearer token still has to ride along, because this file
   * is ADMIN-only. The caller shows the bytes from an object
   * URL; no address for the document is ever kept.
   */
  const session = loadSession();

  const response = await fetch(
    `${LAWYER_API_BASE_URL}/api/admin/lawyers/${encodeURIComponent(
      lawyerId.trim(),
    )}/document`,
    {
      headers: {
        Accept: "application/pdf, image/*, */*",
        ...(session?.token
          ? { Authorization: `Bearer ${session.token}` }
          : {}),
      },
    },
  );

  if (!response.ok) {
    let message = `Document request failed with status ${response.status}.`;

    try {
      const errorData: unknown = await response.json();

      if (
        errorData &&
        typeof errorData === "object" &&
        "detail" in errorData &&
        typeof errorData.detail === "string"
      ) {
        message = errorData.detail;
      }
    } catch {
      /* Keep the default HTTP error message. */
    }

    throw new Error(message);
  }

  return response.blob();
}
