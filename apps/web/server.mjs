import {createReadStream} from "node:fs";
import {readFile, stat} from "node:fs/promises";
import {createServer} from "node:http";
import {extname, join, normalize, relative} from "node:path";
import {fileURLToPath} from "node:url";

const distRoot = fileURLToPath(new URL("./dist", import.meta.url));
const indexPath = join(distRoot, "index.html");
const port = Number.parseInt(process.env.PORT ?? "3000", 10);
const apiUpstream = new URL(process.env.STRUCTURA_API_UPSTREAM ?? "http://api:8000");

const mimeTypes = new Map([
  [".css", "text/css; charset=utf-8"],
  [".html", "text/html; charset=utf-8"],
  [".ico", "image/x-icon"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".png", "image/png"],
  [".svg", "image/svg+xml"],
  [".txt", "text/plain; charset=utf-8"],
  [".webmanifest", "application/manifest+json"],
]);

createServer(async (request, response) => {
  try {
    const url = new URL(request.url ?? "/", `http://${request.headers.host ?? "localhost"}`);
    if (url.pathname.startsWith("/api/")) {
      await proxyApi(request, response, url);
      return;
    }
    await serveStatic(response, url.pathname);
  } catch (error) {
    console.error(error);
    if (!response.headersSent) {
      response.writeHead(500, {"Content-Type": "text/plain; charset=utf-8"});
    }
    response.end("Internal server error");
  }
}).listen(port, "0.0.0.0", () => {
  console.log(`Structura web listening on 0.0.0.0:${port}`);
});

async function proxyApi(request, response, url) {
  const upstreamUrl = new URL(url.pathname + url.search, apiUpstream);
  const headers = new Headers();
  for (const [name, value] of Object.entries(request.headers)) {
    if (value === undefined) {
      continue;
    }
    if (["connection", "host", "keep-alive", "transfer-encoding"].includes(name.toLowerCase())) {
      continue;
    }
    headers.set(name, Array.isArray(value) ? value.join(", ") : value);
  }

  const body = ["GET", "HEAD"].includes(request.method ?? "GET")
    ? undefined
    : await readRequestBody(request);
  const upstreamResponse = await fetch(upstreamUrl, {
    method: request.method,
    headers,
    body,
    redirect: "manual",
  });

  for (const [name, value] of upstreamResponse.headers) {
    if (["connection", "content-encoding", "transfer-encoding"].includes(name.toLowerCase())) {
      continue;
    }
    if (name.toLowerCase() !== "set-cookie") {
      response.setHeader(name, value);
    }
  }

  const setCookie = upstreamResponse.headers.getSetCookie?.() ?? [];
  const fallbackSetCookie = upstreamResponse.headers.get("set-cookie");
  if (setCookie.length > 0) {
    response.setHeader("Set-Cookie", setCookie);
  } else if (fallbackSetCookie) {
    response.setHeader("Set-Cookie", fallbackSetCookie);
  }

  response.writeHead(upstreamResponse.status);
  response.end(Buffer.from(await upstreamResponse.arrayBuffer()));
}

async function serveStatic(response, pathname) {
  const filePath = await resolveStaticPath(pathname);
  const fileStat = await stat(filePath);
  response.writeHead(200, {
    "Cache-Control": filePath === indexPath ? "no-store" : "public, max-age=31536000, immutable",
    "Content-Length": fileStat.size,
    "Content-Type": mimeTypes.get(extname(filePath)) ?? "application/octet-stream",
  });
  createReadStream(filePath).pipe(response);
}

async function resolveStaticPath(pathname) {
  const decoded = decodeURIComponent(pathname);
  const requestedPath = decoded === "/" ? "/index.html" : decoded;
  const normalizedPath = normalize(requestedPath).replace(/^(\.\.(\/|\\|$))+/, "");
  const candidate = join(distRoot, normalizedPath);

  if (relative(distRoot, candidate).startsWith("..")) {
    return indexPath;
  }

  try {
    const fileStat = await stat(candidate);
    return fileStat.isFile() ? candidate : indexPath;
  } catch {
    return indexPath;
  }
}

async function readRequestBody(request) {
  const chunks = [];
  for await (const chunk of request) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  return Buffer.concat(chunks);
}
