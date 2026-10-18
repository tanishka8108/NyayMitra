/* =========================================================
   LAWYER PHOTO + INITIALS HELPERS

   Shared by the avatar component, the search results, the
   profile pages and the registration form. Kept out of the
   component file so hot-reload stays component-only.
   ========================================================= */

const LOCAL_PHOTO_PREFIX = "nyaymitra.lawyerPhoto.";

/**
 * This device's locally stored upload for a lawyer account,
 * if one exists. A stopgap until the backend grows a
 * profile-photo field — never presented as a server photo.
 */
export function localLawyerPhoto(
  lawyerId: string | null | undefined,
): string | null {
  if (!lawyerId) return null;

  try {
    return localStorage.getItem(LOCAL_PHOTO_PREFIX + lawyerId);
  } catch {
    return null;
  }
}

/** Persist this device's copy of an uploaded profile photo. */
export function saveLocalLawyerPhoto(
  lawyerId: string,
  dataUrl: string,
): void {
  try {
    localStorage.setItem(LOCAL_PHOTO_PREFIX + lawyerId, dataUrl);
  } catch {
    /* Quota or private mode — the photo simply stays on the form. */
  }
}


