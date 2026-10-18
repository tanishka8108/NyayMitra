import { useCallback, useEffect, useState } from "react";
import { TriangleAlert } from "lucide-react";

import { TRANSLATION_API_BASE_URL } from "../api/config";
import { getTranslationHealth } from "../api/translationApi";

import "./ServiceStatus.css";

/* =========================================================
   NLP SERVICE STATUS

   Both NLP-backed pages (Translation, Voice) need the
   FastAPI service on port 8001 to be reachable. Checking
   it up-front turns a confusing mid-submit failure into a
   clear message the moment the page opens.

   States:
     checking  first probe in flight
     online    GET /health answered
     offline   service unreachable / unhealthy
   ========================================================= */

type Status = "checking" | "online" | "offline";

export default function ServiceStatus() {
  const [status, setStatus] =
    useState<Status>("checking");

  /* Bumped by "Check again" to re-run the probe. */
  const [attempt, setAttempt] = useState(0);

  const recheck = useCallback(() => {
    setStatus("checking");
    setAttempt((value) => value + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;

    const probe = async () => {
      try {
        await getTranslationHealth();

        /* /health answered — the service is up. */
        if (!cancelled) {
          setStatus("online");
        }
      } catch {
        if (!cancelled) {
          setStatus("offline");
        }
      }
    };

    void probe();

    return () => {
      cancelled = true;
    };
  }, [attempt]);

  /* ---- ONLINE: quiet confirmation only ---- */

  if (status === "online") {
    return (
      <div
        className="service-status service-status-online"
        role="status"
      >
        <span className="service-status-dot" />
        NLP service online
      </div>
    );
  }

  /* ---- CHECKING: no noise, keep the layout stable ---- */

  if (status === "checking") {
    return (
      <div
        className="service-status service-status-checking"
        role="status"
      >
        <span className="service-status-dot" />
        Checking NLP service…
      </div>
    );
  }

  /* ---- OFFLINE: explain and offer a retry ---- */

  return (
    <div
      className="service-status service-status-offline"
      role="alert"
    >
      <span className="service-status-icon"><TriangleAlert size={18} aria-hidden="true" /></span>

      <div className="service-status-body">
        <strong>
          Translation service is offline
        </strong>

        <p>
          NyayMitra could not reach the NLP service at{" "}
          <code>{TRANSLATION_API_BASE_URL}</code>.
          Translation and voice transcription are
          unavailable until it is running.
        </p>
      </div>

      <button type="button" onClick={recheck}>
        Check again
      </button>
    </div>
  );
}
