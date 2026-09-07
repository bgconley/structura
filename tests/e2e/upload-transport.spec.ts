import {expect, test} from "@playwright/test";
import {createServer, type IncomingHttpHeaders} from "node:http";
import {createHash} from "node:crypto";
import {writeFile} from "node:fs/promises";
import {csrfToken, mockStructuraApi} from "./support/structuraMock";
import {installUploadAttemptMock} from "./support/uploadAttemptMock";
import {acceptedUpload} from "./support/uploadAttemptFixture";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "This test owns a disposable loopback raw-byte receiver.");
test("a disk-backed File sends exact raw bytes and only real upload progress reaches saving", async ({page, context}, testInfo) => {
  await context.addCookies([{name: "structura_session", value: "wire-upload", domain: "localhost", path: "/"},
    {name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"}]);
  await mockStructuraApi(page);
  const state = await installUploadAttemptMock(page);
  const bytes = Buffer.from("%PDF-1.7\n% exact disk-backed original bytes\n%%EOF\n");
  const filePath = testInfo.outputPath("raw-original.pdf"); await writeFile(filePath, bytes);
  let received: Buffer | null = null, headers: IncomingHttpHeaders = {};
  let release!: () => void; const held = new Promise<void>((resolve) => {release = resolve;});
  const server = createServer(async (request, response) => {
    response.setHeader("Access-Control-Allow-Origin", "http://localhost:4173");
    response.setHeader("Access-Control-Allow-Credentials", "true");
    response.setHeader("Access-Control-Allow-Headers", "accept,content-type,x-csrf-token,if-match");
    response.setHeader("Access-Control-Allow-Methods", "PUT,OPTIONS");
    if (request.method === "OPTIONS") {response.writeHead(204); response.end(); return;}
    const chunks: Buffer[] = []; for await (const chunk of request) chunks.push(Buffer.from(chunk));
    received = Buffer.concat(chunks); headers = request.headers;
    await held;
    const attempt = [...state.attempts.values()][0];
    const hash = createHash("sha256").update(received).digest("hex"), accepted = acceptedUpload();
    const observation = {...accepted, ...attempt, state: "accepted", actualBytes: received.length, sha256: hash,
      detectedMimeType: "application/pdf", currentTransferId: accepted.currentTransferId,
      receipt: {...accepted.receipt!, sha256: hash, byteSize: received.length}};
    response.setHeader("Content-Type", "application/json"); response.end(JSON.stringify(observation));
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address(); if (!address || typeof address === "string") throw new Error("Loopback receiver did not bind");
  await page.route("**/api/v1/uploads/*/content", (route) => route.continue({url: `http://127.0.0.1:${address.port}${new URL(route.request().url()).pathname}`}));
  try {
    await page.goto("/inbox"); await expect(page.locator(".top-command input[type=file]")).toBeEnabled(); await page.locator(".top-command input[type=file]").setInputFiles(filePath);
    const queue = page.getByRole("dialog", {name: "Upload files"});
    await expect.poll(() => received?.length).toBe(bytes.length);
    expect(received).toEqual(bytes);
    expect(headers["content-type"]).toBe("application/octet-stream"); expect(headers["x-csrf-token"]).toBe(csrfToken);
    expect(headers["if-match"]).toBe([...state.attempts.values()][0].revision);
    await expect(queue).toContainText("Saving original");
    await expect(queue.getByRole("progressbar")).toHaveAttribute("value", String(bytes.length));
    await expect(queue.getByText("Upload accepted", {exact: true})).toHaveCount(0);
    release(); await expect(queue).toContainText("Upload accepted");
  } finally { release(); server.closeAllConnections(); await new Promise<void>((resolve) => server.close(() => resolve())); }
});
