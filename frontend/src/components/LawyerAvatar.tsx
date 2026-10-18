import { useState } from "react";

import { initialsOf } from "../lib/initials";
import { localLawyerPhoto } from "../lib/lawyerPhoto";

/* =========================================================
   LAWYER AVATAR

   One shared picture slot for every place a lawyer is shown:
   search results, profile cards, the full profile page.

   Source order:
     1. the photo the API actually returned
        (``profile_image`` / ``profile_photo`` from the
        lawyers directory — real uploads only, never faked)
     2. a photo this browser's owner uploaded for their own
        lawyer account (stored locally by the registration
        form until the backend grows a profile-photo field)
     3. neutral initials — no stock portraits, no invented
        faces.

   A URL that fails to load falls back to the initials too,
   so a broken link never leaves an empty box.

   With no ``className`` the avatar is a plain circle sized
   by the ``size`` prop (``.nm-avatar``). Passing a
   ``className`` instead lets a screen keep its own branded
   tile shape — the class fully replaces ``nm-avatar`` and
   its CSS owns the size.
   ========================================================= */

type LawyerAvatarProps = {
  name: string;
  /** Server-provided photo URL (profile_image or profile_photo). */
  photo?: string | null;
  /** Fallback to this device's local upload before initials. */
  lawyerId?: string | null;
  /** Circle size in px — ignored when a className is given. */
  size?: number;
  /** Replaces the default .nm-avatar styling entirely. */
  className?: string;
};

function LawyerAvatar({
  name,
  photo,
  lawyerId,
  size = 46,
  className,
}: LawyerAvatarProps) {
  const [failed, setFailed] = useState(false);

  const remote = photo?.trim() || null;
  const local = failed ? null : localLawyerPhoto(lawyerId);
  const src = remote || local;

  return (
    <div
      className={className ?? "nm-avatar"}
      style={
        className
          ? undefined
          : {
              width: size,
              height: size,
              fontSize: Math.max(11, Math.round(size * 0.34)),
            }
      }
    >
      {src ? (
        <img
          src={src}
          alt=""
          aria-hidden="true"
          onError={() => setFailed(true)}
        />
      ) : (
        <span aria-hidden="true">{initialsOf(name)}</span>
      )}
    </div>
  );
}

export default LawyerAvatar;
