/**
 * Playwright global setup: authenticate once before the suite runs and persist
 * the session cookie as Playwright `storageState`.
 *
 * Why this is needed: the backend now requires an authenticated session for
 * every canvas / conversation endpoint (per-user isolation, #36) and the
 * frontend route guard redirects unauthenticated browsers to /login (#38). So
 * every E2E test — both the `request` fixture / `page.request` calls that seed
 * canvases AND the browser `page` that drives the UI — must present a valid
 * session cookie. Logging in once here and sharing the cookie via
 * `use.storageState` covers both: Playwright injects the stored cookie into
 * every browser context and every APIRequestContext created from the project.
 *
 * CSRF note: /auth/register and /auth/login are state-changing routes guarded
 * by `verify_origin`. We send an `Origin` header equal to the backend host so
 * the same-origin check passes (the APIRequestContext does not set one by
 * default).
 *
 * The E2E user is registered idempotently: on a fresh CI DB the register
 * succeeds; when the backend is reused locally the user already exists and
 * register returns 409, which we ignore before logging in.
 */
import { request as playwrightRequest } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { dirname } from "node:path";

const API_BASE = "http://localhost:8000/api";
const EMAIL = "e2e@agentgraphstudio.test";
const PASSWORD = "e2e-test-password-1234";
const STORAGE_STATE_PATH = "e2e/.auth/user.json";

export default async function globalSetup() {
  const context = await playwrightRequest.newContext({
    extraHTTPHeaders: { Origin: "http://localhost:8000" },
  });

  try {
    const registerRes = await context.post(`${API_BASE}/auth/register`, {
      data: { email: EMAIL, password: PASSWORD },
    });
    // 201 = created, 409 = already exists on a reused backend. Anything else
    // is a real failure (e.g. backend down, CSRF blocked) and should fail the
    // suite loudly.
    if (!registerRes.ok() && registerRes.status() !== 409) {
      throw new Error(
        `E2E global setup: register failed with ${registerRes.status()}: ${await registerRes.text()}`
      );
    }

    const loginRes = await context.post(`${API_BASE}/auth/login`, {
      data: { email: EMAIL, password: PASSWORD },
    });
    if (!loginRes.ok()) {
      throw new Error(
        `E2E global setup: login failed with ${loginRes.status()}: ${await loginRes.text()}`
      );
    }

    // Persist cookies (the agentbuilder_session cookie set by the backend) so
    // every test context starts authenticated. Ensure the destination directory
    // exists — storageState does not create parent directories.
    mkdirSync(dirname(STORAGE_STATE_PATH), { recursive: true });
    await context.storageState({ path: STORAGE_STATE_PATH });
  } finally {
    await context.dispose();
  }
}