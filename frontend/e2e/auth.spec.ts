/**
 * E2E coverage for the frontend auth shell (#38): route guard redirect,
 * login page, and register page, exercised against the real backend.
 *
 * The suite-wide `use.storageState` (see playwright.config.ts) starts every
 * test authenticated. Tests that need a fresh, unauthenticated browser
 * override `storageState` to an empty cookie jar for their describe block.
 */
import { test, expect } from "@playwright/test";

const E2E_USER = {
  email: "e2e@agentgraphstudio.test",
  password: "e2e-test-password-1234",
};

// Unauthenticated browser: no cookies. Used for guard-redirect and login/register flow tests.
const NO_AUTH = { storageState: { cookies: [], origins: [] } as const };

test.describe("Auth — route guard", () => {
  test.use(NO_AUTH);

  test("redirects an unauthenticated user from '/' to /login", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  });

  test("redirects an unauthenticated user from a canvas route to /login", async ({ page }) => {
    await page.goto("/canvas/abc");
    await expect(page).toHaveURL(/\/login$/);
  });
});

test.describe("Auth — login page", () => {
  test.use(NO_AUTH);

  test("renders the login form and a link to register", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByLabel("Password", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Log in" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Register" })).toBeVisible();
  });

  test("logs in with valid credentials and lands on the app", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill(E2E_USER.email);
    await page.getByLabel("Password", { exact: true }).fill(E2E_USER.password);
    await page.getByRole("button", { name: "Log in" }).click();

    // The e2e user was registered by global-setup, so login succeeds and the
    // route guard lets us through to the landing page ("New Canvas" button).
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("button", { name: "New Canvas" })).toBeVisible({ timeout: 10_000 });
  });

  test("shows an inline error for invalid credentials", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill(E2E_USER.email);
    await page.getByLabel("Password", { exact: true }).fill("wrong-password");
    await page.getByRole("button", { name: "Log in" }).click();

    await expect(page.getByRole("alert")).toContainText(/Invalid email or password/i);
    // Stays on the login page.
    await expect(page).toHaveURL(/\/login$/);
  });
});

test.describe("Auth — register page", () => {
  test.use(NO_AUTH);

  test("renders the register form and a link to log in", async ({ page }) => {
    await page.goto("/register");
    await expect(page.getByRole("heading", { name: "Create your account" })).toBeVisible();
    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByLabel("Password", { exact: true })).toBeVisible();
    await expect(page.getByLabel("Confirm password")).toBeVisible();
    await expect(page.getByRole("button", { name: "Create account" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Log in" })).toBeVisible();
  });

  test("registers a new account and lands on the app", async ({ page }) => {
    const uniqueEmail = `e2e-register-${Date.now()}@agentgraphstudio.test`;
    await page.goto("/register");
    await page.getByLabel("Email").fill(uniqueEmail);
    await page.getByLabel("Password", { exact: true }).fill(E2E_USER.password);
    await page.getByLabel("Confirm password").fill(E2E_USER.password);
    await page.getByRole("button", { name: "Create account" }).click();

    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("button", { name: "New Canvas" })).toBeVisible({ timeout: 10_000 });
  });
});

test.describe("Auth — already authenticated", () => {
  // Uses the suite-wide storageState (authenticated).

  test("redirects an authenticated user from /login to the app", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("button", { name: "New Canvas" })).toBeVisible({ timeout: 10_000 });
    await expect(page).toHaveURL(/\/$/);
  });

  test("redirects an authenticated user from /register to the app", async ({ page }) => {
    await page.goto("/register");
    await expect(page.getByRole("button", { name: "New Canvas" })).toBeVisible({ timeout: 10_000 });
    await expect(page).toHaveURL(/\/$/);
  });
});

// Account management (#39): change password + logout other sessions. Uses a
// throwaway user registered within the test so the shared e2e user's password
// is never mutated (which would break the rest of the suite).
test.describe("Account — change password", () => {
  test.use(NO_AUTH);

  test("changes the password, keeps this session, and invalidates the old password", async ({ page, request }) => {
    const email = `e2e-acct-${Date.now()}@agentgraphstudio.test`;
    const oldPassword = "e2e-old-password-1234";
    const newPassword = "e2e-new-password-5678";

    // Register + log in as the throwaway user through the UI so the browser
    // holds the session cookie for /account.
    await page.goto("/register");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(oldPassword);
    await page.getByLabel("Confirm password").fill(oldPassword);
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("button", { name: "New Canvas" })).toBeVisible({ timeout: 10_000 });

    // Open the account page from the landing-page header.
    await page.getByRole("link", { name: "Account" }).click();
    await expect(page).toHaveURL(/\/account$/);
    await expect(page.getByRole("heading", { name: "Account" })).toBeVisible();
    await expect(page.getByText(email)).toBeVisible();

    // Change the password.
    await page.getByLabel("Current password").fill(oldPassword);
    await page.getByLabel("New password", { exact: true }).fill(newPassword);
    await page.getByLabel("Confirm new password").fill(newPassword);
    await page.getByRole("button", { name: "Change password" }).click();
    await expect(page.getByText(/Password changed/i)).toBeVisible({ timeout: 10_000 });

    // The current (this browser) session is still alive — the account page did
    // not bounce to /login. Use page.request (shares the page's cookie jar =
    // the throwaway user's session) rather than the `request` fixture, which
    // carries the suite-wide shared-e2e-user cookie.
    const meRes = await page.request.get("http://localhost:8000/api/auth/me");
    expect(meRes.status()).toBe(200);

    // The old password no longer logs in; the new one does. These are
    // email/password based, so the cookie the request fixture carries is
    // irrelevant — send the same-origin Origin header for the CSRF check.
    const oldLogin = await request.post("http://localhost:8000/api/auth/login", {
      data: { email, password: oldPassword },
      headers: { Origin: "http://localhost:8000" },
    });
    expect(oldLogin.status()).toBe(401);

    const newLogin = await request.post("http://localhost:8000/api/auth/login", {
      data: { email, password: newPassword },
      headers: { Origin: "http://localhost:8000" },
    });
    expect(newLogin.status()).toBe(200);
  });
});

test.describe("Account — logout other sessions", () => {
  // Uses the suite-wide authenticated storageState for the calling browser,
  // then opens a SECOND session for the same e2e user from an isolated API
  // context (so it doesn't overwrite the calling browser's cookie) and proves
  // that second session is revoked after the action.
  test("revokes other sessions while keeping the current one", async ({ page, request, playwright }) => {
    // Second "device": log the shared e2e user in via a FRESH, isolated API
    // context so the login Set-Cookie does not clobber the suite-wide
    // storageState cookie in the `request` fixture's jar.
    const secondCtx = await playwright.request.newContext({
      extraHTTPHeaders: { Origin: "http://localhost:8000" },
    });
    try {
      const loginRes = await secondCtx.post("http://localhost:8000/api/auth/login", {
        data: { email: E2E_USER.email, password: E2E_USER.password },
      });
      expect(loginRes.status()).toBe(200);
      const secondCookie = (await loginRes.headersArray())["set-cookie"]?.find((c) =>
        c.startsWith("agentbuilder_session=")
      );
      expect(secondCookie).toBeTruthy();
      const secondToken = secondCookie!.split("=")[1].split(";")[0];

      // The second session is alive before the action.
      const beforeMe = await secondCtx.get("http://localhost:8000/api/auth/me", {
        headers: { Cookie: `agentbuilder_session=${secondToken}` },
      });
      expect(beforeMe.status()).toBe(200);

      // The calling browser (suite-wide storageState, untouched) opens /account
      // and clicks "Log out other sessions".
      await page.goto("/account");
      await expect(page.getByRole("heading", { name: "Account" })).toBeVisible({ timeout: 10_000 });
      await page.getByRole("button", { name: "Log out other sessions" }).click();
      await expect(page.getByText(/signed out/i)).toBeVisible({ timeout: 10_000 });

      // The second device's session cookie is now dead — /auth/me 401s.
      const afterMe = await secondCtx.get("http://localhost:8000/api/auth/me", {
        headers: { Cookie: `agentbuilder_session=${secondToken}` },
      });
      expect(afterMe.status()).toBe(401);
    } finally {
      await secondCtx.dispose();
    }

    // The calling browser is still authenticated (its cookie jar was never
    // touched by the isolated second-device context).
    const myMe = await request.get("http://localhost:8000/api/auth/me");
    expect(myMe.status()).toBe(200);
  });
});