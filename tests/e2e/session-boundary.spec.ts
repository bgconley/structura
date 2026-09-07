import {expect, test, type Page, type Route} from "@playwright/test";
import {apiOrigin, csrfToken, mockStructuraApi} from "./support/structuraMock";

test.skip(process.env.STRUCTURA_E2E_LIVE === "1", "Session browser regressions use an isolated mock API.");

const headers = {
  "Access-Control-Allow-Origin": "http://localhost:4173",
  "Access-Control-Allow-Credentials": "true",
  "Access-Control-Allow-Headers": "accept,content-type,x-csrf-token",
  "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
};
const session = {sessionId: "session-a", userId: "person-a", householdId: "household-a",
  displayName: "Alex Reviewer", email: "alex@example.com", isAuthenticated: true,
  sessionCookieName: "structura_session", csrfCookieName: "structura_csrf"};

function gate() {
  let release!: () => void;
  const promise = new Promise<void>((resolve) => { release = resolve; });
  return {promise, release};
}

async function authRoute(page: Page, handle: (route: Route) => Promise<void>) {
  await page.route(`${apiOrigin}/api/v1/auth/session`, async (route) => {
    if (route.request().method() === "OPTIONS") {
      await route.fulfill({status: 204, headers});
    } else await handle(route);
  });
}

async function login(page: Page) {
  await page.getByRole("textbox", {name: "Email"}).fill("alex@example.com");
  await page.getByLabel("Password").fill("correct-password");
  await page.getByRole("button", {name: "Sign in", exact: true}).click();
}

test.beforeEach(async ({page, context}) => {
  await context.addCookies([{name: "structura_csrf", value: csrfToken, domain: "localhost", path: "/"}]);
  await mockStructuraApi(page);
});

test("login has one pending request, retains failures and uses the returned identity", async ({page}) => {
  let attempts = 0;
  const pending = gate();
  await authRoute(page, async (route) => {
    if (route.request().method() === "GET") return route.fulfill({status: 401, headers, json: {detail: "Not authenticated"}});
    attempts += 1;
    expect(route.request().postDataJSON()).toEqual({method: "password", email: "alex@example.com", password: "correct-password"});
    await pending.promise;
    await route.fulfill(attempts === 1
      ? {status: 401, headers, json: {detail: "Invalid sign-in credentials."}}
      : {status: 201, headers, json: session});
  });
  await page.goto("/");
  await login(page);
  await expect(page.getByRole("button", {name: "Signing in..."})).toBeDisabled();
  await page.locator("form").evaluate((form: HTMLFormElement) => form.requestSubmit());
  expect(attempts).toBe(1);
  pending.release();
  await expect(page.getByRole("alert")).toHaveText("Invalid sign-in credentials.");
  await expect(page.getByLabel("Password")).toHaveValue("correct-password");
  await page.getByRole("button", {name: "Sign in", exact: true}).click();
  await expect(page.getByLabel("Account: Alex Reviewer")).toBeVisible();
  await expect(page.getByRole("row", {name: /Existing Warranty/})).toBeVisible();
  expect(attempts).toBe(2);
});

test("login rediscovers a custom CSRF binding after local session state was cleared", async ({page, context}) => {
  await context.addCookies([{name: "private_csrf", value: "current-session-binding", domain: "localhost", path: "/"}]);
  let posts = 0;
  await authRoute(page, async (route) => {
    if (route.request().method() === "POST") {
      posts += 1;
      expect(route.request().headers()["x-csrf-token"]).toBe("current-session-binding");
      return route.fulfill({status: 201, headers, json: {...session, sessionId: "session-b"}});
    }
    await route.fulfill({headers, json: {...session, csrfCookieName: "private_csrf"}});
  });
  await page.route(`${apiOrigin}/api/v1/review-tasks*`, (route) => route.fulfill({status: 401, headers, json: {detail: "Not authenticated"}}));
  await page.goto("/");
  await page.getByRole("button", {name: /Review Queue/}).click();
  await expect(page.getByRole("button", {name: "Sign in", exact: true})).toBeVisible();
  await login(page);
  await expect(page.getByLabel("Account: Alex Reviewer")).toBeVisible();
  expect(posts).toBe(1);
});

test("an unavailable login preflight never posts credentials and can be retried", async ({page}) => {
  let posts = 0;
  let unavailable = false;
  await authRoute(page, async (route) => {
    if (route.request().method() === "POST") {
      posts += 1;
      return route.fulfill({status: 201, headers, json: session});
    }
    await route.fulfill(unavailable
      ? {status: 503, headers, json: {detail: "Unavailable"}}
      : {status: 401, headers, json: {detail: "Not authenticated"}});
  });
  await page.goto("/");
  await expect(page.getByRole("button", {name: "Sign in", exact: true})).toBeVisible();
  unavailable = true;
  await login(page);
  await expect(page.getByRole("alert")).toHaveText("Unavailable");
  await expect(page.getByLabel("Password")).toHaveValue("correct-password");
  expect(posts).toBe(0);
  unavailable = false;
  await page.getByRole("button", {name: "Sign in", exact: true}).click();
  await expect(page.getByLabel("Account: Alex Reviewer")).toBeVisible();
  expect(posts).toBe(1);
});

test("a late login preflight cannot post after another tab changes the session", async ({page}) => {
  let posts = 0;
  let signedInElsewhere = false;
  await authRoute(page, async (route) => {
    if (route.request().method() === "POST") {
      posts += 1;
      return route.fulfill({status: 201, headers, json: session});
    }
    await route.fulfill(signedInElsewhere
      ? {headers, json: {...session, sessionId: "session-b", displayName: "Blair Reviewer"}}
      : {status: 401, headers, json: {detail: "Not authenticated"}});
  });
  await page.goto("/");
  await expect(page.getByRole("button", {name: "Sign in", exact: true})).toBeVisible();
  await page.evaluate(() => {
    const original = window.fetch;
    let intercept = true;
    window.fetch = (input, init) => {
      if (intercept && String(input).endsWith("/api/v1/auth/session") && !init?.method) {
        intercept = false;
        return new Promise<Response>((resolve) => {
          Object.assign(window, {releaseLoginPreflight: resolve});
        });
      }
      return original(input, init);
    };
  });
  await login(page);
  await expect(page.getByRole("button", {name: "Signing in..."})).toBeDisabled();
  signedInElsewhere = true;
  await page.evaluate(() => {
    const connection = new BroadcastChannel("structura-session");
    connection.postMessage({type: "signed-in"});
    connection.close();
  });
  await expect(page.getByLabel("Account: Blair Reviewer")).toBeVisible();
  await page.evaluate(async (previous) => {
    const state = window as unknown as {releaseLoginPreflight: (response: Response) => void};
    state.releaseLoginPreflight(new Response(JSON.stringify(previous)));
    await new Promise((resolve) => window.setTimeout(resolve, 0));
  }, session);
  expect(posts).toBe(0);
  await expect(page.getByLabel("Account: Blair Reviewer")).toBeVisible();
});

test("a login in another tab clears old account state before the replacement check returns", async ({page, context}) => {
  const other = await context.newPage();
  const pending = gate();
  let switched = false;
  await mockStructuraApi(other);
  await authRoute(page, async (route) => {
    if (switched) await pending.promise;
    await route.fulfill({headers, json: switched
      ? {...session, sessionId: "session-b", displayName: "Blair Reviewer"} : session});
  });
  await authRoute(other, async (route) => {
    if (route.request().method() === "POST") {
      switched = true;
      return route.fulfill({status: 201, headers, json: {...session, sessionId: "session-b", displayName: "Blair Reviewer"}});
    }
    await route.fulfill({status: 401, headers, json: {detail: "Not authenticated"}});
  });
  await page.goto("/");
  await expect(page.getByRole("row", {name: /Existing Warranty/})).toBeVisible();
  await page.locator(".inspector").getByLabel("Title", {exact: true}).fill("Previous account private edit");
  await other.goto("/");
  await login(other);
  await expect(other.getByLabel("Account: Blair Reviewer")).toBeVisible();
  await expect(page.locator(".app-shell")).toHaveCount(0);
  await expect(page.getByRole("status")).toHaveText("Checking your session...");
  pending.release();
  await expect(page.getByLabel("Account: Blair Reviewer")).toBeVisible();
  await expect(page.locator('input[value="Previous account private edit"]')).toHaveCount(0);
  await other.close();
});

test("keyboard account control signs out with reported CSRF cookie and accepts an empty204", async ({page, context}, info) => {
  await context.addCookies([{name: "private_csrf", value: "bound-private-csrf", domain: "localhost", path: "/"}]);
  const pending = gate();
  let deletes = 0;
  await authRoute(page, async (route) => {
    if (route.request().method() === "DELETE") {
      deletes += 1;
      expect(route.request().headers()["x-csrf-token"]).toBe("bound-private-csrf");
      await pending.promise;
      return route.fulfill({status: 204, headers});
    }
    await route.fulfill({headers, json: {...session, csrfCookieName: "private_csrf"}});
  });
  await page.goto("/");
  await expect(page.getByRole("row", {name: /Existing Warranty/})).toBeVisible();
  const account = page.getByLabel("Account: Alex Reviewer");
  await account.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("alex@example.com", {exact: true})).toBeVisible();
  await page.screenshot({path: info.outputPath("session-menu-desktop.png"), fullPage: true});
  await page.keyboard.press("Escape");
  await expect(account).toBeFocused();
  await page.keyboard.press("Enter");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", {name: "Sign out", exact: true})).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toHaveText("Signing out...");
  await expect(page.getByText("Existing Warranty", {exact: true})).toHaveCount(0);
  pending.release();
  await expect(page.getByRole("status")).toHaveText("You have signed out.");
  await expect(page.getByLabel("Password")).toHaveValue("");
  expect(deletes).toBe(1);
});

test("failed logout hides documents and offers a truthful retry", async ({page}) => {
  let deletes = 0;
  await authRoute(page, async (route) => {
    if (route.request().method() !== "DELETE") return route.fulfill({headers, json: session});
    deletes += 1;
    await route.fulfill(deletes === 1 ? {status: 503, headers, json: {detail: "Unavailable"}} : {status: 204, headers});
  });
  await page.goto("/");
  await page.getByLabel("Account: Alex Reviewer").click();
  await page.getByRole("button", {name: "Sign out", exact: true}).click();
  await expect(page.getByRole("status")).toContainText("Sign-out could not be confirmed");
  await expect(page.locator(".app-shell")).toHaveCount(0);
  await page.getByRole("button", {name: "Try signing out again"}).click();
  await expect(page.getByRole("status")).toHaveText("You have signed out.");
});

test("a protected401 expires the complete workbench but a403 does not", async ({page}) => {
  await authRoute(page, (route) => route.fulfill({headers, json: session}));
  let deniedStatus = 403;
  await page.route(`${apiOrigin}/api/v1/review-tasks*`, (route) => route.fulfill({status: deniedStatus, headers, json: {detail: "Not permitted"}}));
  await page.goto("/");
  await page.getByRole("button", {name: /Review Queue/}).click();
  await expect(page.getByLabel("Account: Alex Reviewer")).toBeVisible();
  await expect(page.getByText("Not permitted", {exact: true})).toBeVisible();
  deniedStatus = 401;
  await page.getByRole("button", {name: /Inbox/}).click();
  await page.getByRole("button", {name: /Review Queue/}).click();
  await expect(page.getByRole("status")).toHaveText("Your session has ended. Sign in again to continue.");
  await expect(page.locator(".app-shell")).toHaveCount(0);
});

test("known expiry removes private data even without another API request", async ({page}) => {
  await page.clock.install();
  const now = await page.evaluate(() => Date.now());
  await authRoute(page, (route) => route.fulfill({headers, json: {...session, expiresAt: new Date(now + 60_000).toISOString()}}));
  await page.goto("/");
  await expect(page.getByRole("row", {name: /Existing Warranty/})).toBeVisible();
  await page.clock.fastForward(61_000);
  await expect(page.getByRole("status")).toHaveText("Your session has ended. Sign in again to continue.");
  await expect(page.locator(".app-shell")).toHaveCount(0);
});

test("long-session absolute expiry survives the browser timer cap and offline rechecks", async ({page}) => {
  await page.clock.install();
  const now = await page.evaluate(() => Date.now());
  const lifetime = 30 * 24 * 60 * 60 * 1000;
  const timerCap = 2_147_483_647;
  let unavailable = false;
  let offlineChecks = 0;
  await authRoute(page, (route) => {
    if (unavailable) {
      offlineChecks += 1;
      return route.fulfill({status: 503, headers, json: {detail: "Unavailable"}});
    }
    return route.fulfill({headers, json: {...session, expiresAt: new Date(now + lifetime).toISOString()}});
  });
  await page.goto("/");
  await expect(page.getByRole("row", {name: /Existing Warranty/})).toBeVisible();
  unavailable = true;
  // Playwright also bounds a single numeric jump to a signed 32-bit value.
  await page.clock.fastForward(timerCap - 1000);
  await page.clock.fastForward(1001);
  await expect.poll(() => offlineChecks).toBeGreaterThan(0);
  await expect(page.getByRole("row", {name: /Existing Warranty/})).toBeVisible();
  await page.clock.fastForward(lifetime - timerCap);
  await expect(page.getByRole("status")).toHaveText("Your session has ended. Sign in again to continue.");
  await expect(page.locator(".app-shell")).toHaveCount(0);
});

test("foreground revalidation removes a revoked session", async ({page}) => {
  let revoked = false;
  await authRoute(page, (route) => route.fulfill(revoked ? {status: 401, headers, json: {detail: "Not authenticated"}} : {headers, json: session}));
  await page.goto("/");
  await expect(page.getByRole("row", {name: /Existing Warranty/})).toBeVisible();
  revoked = true;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("button", {name: "Sign in", exact: true})).toBeVisible();
  await expect(page.locator(".app-shell")).toHaveCount(0);
});

test("a session-check outage is retryable and is not reported as bad credentials", async ({page}) => {
  let unavailable = true;
  await authRoute(page, (route) => route.fulfill(unavailable ? {status: 503, headers, json: {detail: "Unavailable"}} : {headers, json: session}));
  await page.goto("/");
  await expect(page.getByRole("status")).toContainText("Unable to check your session");
  await expect(page.getByLabel("Password")).toHaveCount(0);
  unavailable = false;
  await page.getByRole("button", {name: "Retry connection"}).click();
  await expect(page.getByLabel("Account: Alex Reviewer")).toBeVisible();
});

test("logout invalidates the same session in another open tab", async ({page, context}) => {
  const other = await context.newPage();
  await mockStructuraApi(other);
  for (const tab of [page, other]) {
    await authRoute(tab, (route) => route.fulfill(route.request().method() === "DELETE"
      ? {status: 204, headers} : {headers, json: session}));
    await tab.goto("/");
    await expect(tab.getByLabel("Account: Alex Reviewer")).toBeVisible();
  }
  await page.getByLabel("Account: Alex Reviewer").click();
  await page.getByRole("button", {name: "Sign out", exact: true}).click();
  await expect(other.getByRole("status")).toHaveText("Your session has ended. Sign in again to continue.");
  await expect(other.locator(".app-shell")).toHaveCount(0);
  await other.close();
});

test("a changed session replaces private component state before loading the new account", async ({page}) => {
  let switched = false;
  await authRoute(page, (route) => route.fulfill({headers, json: switched
    ? {...session, sessionId: "session-b", userId: "person-b", displayName: "Blair Reviewer"} : session}));
  await page.goto("/");
  await expect(page.getByRole("row", {name: /Existing Warranty/})).toBeVisible();
  await page.locator(".inspector").getByLabel("Title", {exact: true}).fill("Private unsaved title");
  switched = true;
  await page.route(/\/api\/v1\/documents(?:\?.*)?$/, (route) => route.fulfill({headers, json: {items: [], total: 0}}));
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByLabel("Account: Blair Reviewer")).toBeVisible();
  await expect(page.getByText("No inbox documents yet", {exact: true})).toBeVisible();
  await expect(page.locator('input[value="Private unsaved title"]')).toHaveCount(0);
});

test("session controls preserve the reference shell geometry and fit mobile width", async ({page}, info) => {
  await authRoute(page, (route) => route.fulfill({headers, json: session}));
  await page.goto("/");
  await expect(page.getByLabel("Account: Alex Reviewer")).toBeVisible();
  expect((await page.locator(".sidebar").boundingBox())?.width).toBe(176);
  expect((await page.locator(".top-command").boundingBox())?.height).toBe(56);
  await page.setViewportSize({width: 390, height: 844});
  await page.getByLabel("Account: Alex Reviewer").click();
  await expect(page.getByRole("button", {name: "Sign out", exact: true})).toBeVisible();
  const menu = await page.locator(".session-menu-panel").boundingBox();
  expect(menu!.x).toBeGreaterThanOrEqual(0);
  expect(menu!.x + menu!.width).toBeLessThanOrEqual(390);
  await page.screenshot({path: info.outputPath("session-menu-mobile.png"), fullPage: true});
});

for (const status of [200, 401]) {
  test(`late previous-session${status} cannot publish data or expire a new login`, async ({page}) => {
    let signedOut = false;
    await authRoute(page, async (route) => {
      if (route.request().method() === "DELETE") { signedOut = true; return route.fulfill({status: 204, headers}); }
      await route.fulfill({headers, json: signedOut ? {...session, sessionId: "session-b", displayName: "Blair Reviewer"} : session});
    });
    await page.goto("/");
    await expect(page.getByRole("row", {name: /Existing Warranty/})).toBeVisible();
    // Simulate a transport/body already in flight that ignores abort; the final
    // ownership check must still reject its response rather than publishing it.
    await page.evaluate(async () => {
      const api = await import("/src/api.ts");
      const original = window.fetch;
      let release!: (response: Response) => void;
      window.fetch = (input, init) => String(input).endsWith("/old-session-response")
        ? new Promise<Response>((resolve) => { release = resolve; }) : original(input, init);
      const result = api.fetchJson("/old-session-response").then(() => "published", (error: Error) => error.name);
      Object.assign(window, {releaseOldResponse: release, oldResponseResult: result});
    });
    await page.getByLabel("Account: Alex Reviewer").click();
    await page.getByRole("button", {name: "Sign out", exact: true}).click();
    await login(page);
    await expect(page.getByLabel("Account: Blair Reviewer")).toBeVisible();
    const result = await page.evaluate(async (code) => {
      const state = window as unknown as {releaseOldResponse: (response: Response) => void; oldResponseResult: Promise<string>};
      state.releaseOldResponse(new Response(JSON.stringify({detail: "Expired", secret: "previous account"}), {status: code}));
      return state.oldResponseResult;
    }, status);
    expect(result).toBe("AbortError");
    await expect(page.getByLabel("Account: Blair Reviewer")).toBeVisible();
  });
}
