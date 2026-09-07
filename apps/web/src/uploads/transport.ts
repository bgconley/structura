import {apiBaseUrl, csrfToken} from "../api";
import {sessionRequestScope} from "../sessionRequests";
import {parseUploadAttempt} from "./authority";
import {uploadHttpError} from "./api";
import type {UploadAttempt, UploadIdentity} from "./types";

export type UploadTransfer = UploadIdentity & {uploadId: string; revision: string; replaceTransferId?: string};
export function sendUploadContent(file: File, transfer: UploadTransfer, options: {
  signal: AbortSignal; timeoutMs: number; onProgress: (sentBytes: number, totalBytes: number) => void;
}): Promise<UploadAttempt> {
  const scope = sessionRequestScope(options.signal);
  scope.assertCurrent();
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    let settled = false;
    const stop = () => xhr.abort();
    function finish(action: () => void) {
      if (settled) return;
      settled = true; scope.signal.removeEventListener("abort", stop); action();
    }
    xhr.open("PUT", `${apiBaseUrl}/api/v1/uploads/${encodeURIComponent(transfer.uploadId)}/content`);
    xhr.withCredentials = true;
    xhr.responseType = "json";
    xhr.timeout = options.timeoutMs;
    xhr.setRequestHeader("Accept", "application/json");
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.setRequestHeader("X-CSRF-Token", csrfToken());
    xhr.setRequestHeader("If-Match", transfer.revision);
    if (transfer.replaceTransferId) xhr.setRequestHeader("X-Replace-Transfer-ID", transfer.replaceTransferId);
    xhr.upload.onprogress = (event) => {
      if (settled || scope.signal.aborted) return;
      options.onProgress(Math.min(event.loaded, file.size), file.size);
    };
    xhr.onload = () => finish(() => {
      try {
        scope.assertCurrent();
        if (xhr.status < 200 || xhr.status >= 300) {
          if (xhr.status === 401) scope.unauthorized();
          throw uploadHttpError(xhr.status, xhr.response, xhr.getResponseHeader("Retry-After"));
        }
        resolve(parseUploadAttempt(xhr.response, transfer));
      } catch (failure) { reject(failure); }
    });
    xhr.onerror = () => finish(() => reject(new Error("The transfer response was lost. Check the upload outcome before sending again.")));
    xhr.ontimeout = () => finish(() => reject(new Error("The transfer timed out. Check the upload outcome before sending again.")));
    xhr.onabort = () => finish(() => reject(new DOMException("Upload transport stopped; acceptance is not yet known.", "AbortError")));
    scope.signal.addEventListener("abort", stop, {once: true});
    try { scope.assertCurrent(); xhr.send(file); }
    catch (failure) { finish(() => reject(failure)); }
  });
}
