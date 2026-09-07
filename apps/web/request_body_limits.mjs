/** Stream bounds for the proxy. Declared length is an early check, never authority. */
export const LEGACY_MULTIPART_ALLOWANCE = 64 * 1024;
export const UPLOAD_CONTROL_BYTES = 16 * 1024;

export function requestBodyLimit(method, pathname, maximumFileBytes) {
  if (method === "POST" && /^\/api\/v1\/uploads\/?$/.test(pathname)) {
    return UPLOAD_CONTROL_BYTES;
  }
  if (method === "POST" && /^\/api\/v1\/uploads\/[^/]+\/decision\/?$/.test(pathname)) {
    return UPLOAD_CONTROL_BYTES;
  }
  if (method === "DELETE" && /^\/api\/v1\/uploads\/[^/]+\/?$/.test(pathname)) {
    return UPLOAD_CONTROL_BYTES;
  }
  if (method === "POST" && /^\/api\/v1\/documents\/?$/.test(pathname)) {
    return maximumFileBytes + LEGACY_MULTIPART_ALLOWANCE;
  }
  return maximumFileBytes;
}

export function declaredBodyTooLarge(request, maximum) {
  const value = request.headers["content-length"];
  if (value === undefined) return false;
  if (Array.isArray(value) || !/^(0|[1-9][0-9]*)$/.test(value)) return true;
  const length = Number(value);
  return !Number.isSafeInteger(length) || length > maximum;
}

export function boundedRequestBody(request, maximum) {
  const state = {exceeded: false};
  state.body = (async function* () {
    let total = 0;
    // Keep the response socket alive long enough to deliver a safe 413.
    for await (const chunk of request.iterator({destroyOnReturn: false})) {
      total += chunk.length;
      if (total > maximum) {
        state.exceeded = true;
        throw new Error("Request body exceeds proxy limit");
      }
      yield chunk;
    }
  })();
  return state;
}

export function rejectOversize(request, response) {
  response.writeHead(413, {"Content-Type": "text/plain; charset=utf-8", "Connection": "close"});
  response.once("finish", () => request.destroy());
  response.end("Request body exceeds proxy limit");
}
