import {useEffect, useMemo, useRef, useSyncExternalStore} from "react";
import {UploadQueueController} from "./UploadQueueController";
import type {UploadReceipt} from "./types";
import type {SessionInfo} from "../types";

export function useUploadQueue(session: SessionInfo, onAccepted: (receipt: UploadReceipt) => void | Promise<void>) {
  const callback = useRef(onAccepted); callback.current = onAccepted;
  const controller = useMemo(() => new UploadQueueController({userId: session.userId ?? "", householdId: session.householdId ?? ""},
    (receipt) => callback.current(receipt)), [session.sessionId, session.userId, session.householdId]);
  const state = useSyncExternalStore(controller.subscribe, controller.snapshot);
  useEffect(() => {
    controller.start();
    const online = () => controller.setOnline(navigator.onLine);
    window.addEventListener("online", online); window.addEventListener("offline", online);
    return () => { controller.dispose(); window.removeEventListener("online", online); window.removeEventListener("offline", online); };
  }, [controller]);
  return {state, controller};
}
