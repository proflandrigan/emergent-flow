import { useEffect, useRef } from "react";

import { useTourStore } from "../store/tourStore";
import { useViewLinkStore } from "../store/viewLinkStore";
import { useSessionStore } from "./sessionStore";

/** Keep tour playback consistent with the session's live tour collection (issue #171). */
export function useTourSync(): void {
  const sessionId = useSessionStore((s) => s.sessionId);
  const tours = useSessionStore((s) => s.tours);
  const playing = useTourStore((s) => s.playing);
  const previousSessionId = useRef(sessionId);

  // A different (or no) session invalidates whatever tour was playing.
  useEffect(() => {
    if (previousSessionId.current === sessionId) return;
    previousSessionId.current = sessionId;
    if (useTourStore.getState().playing !== null) {
      useTourStore.getState().exit({ restore: false });
    }
  }, [sessionId]);

  // Follow remote edits/deletes of the playing tour.
  useEffect(() => {
    if (!playing) return;
    const live = tours[playing.tour.id];
    if (!live) {
      // The session effect above may already have exited playback (session switch/leave).
      if (useTourStore.getState().playing === null) return;
      useTourStore.getState().exit();
      useViewLinkStore.getState().addNotice("Tour deleted");
      return;
    }
    if (JSON.stringify(live) !== JSON.stringify(playing.tour)) {
      useTourStore.getState().updateTour(live);
    }
  }, [tours, playing]);
}
