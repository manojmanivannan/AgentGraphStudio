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
    await expect(page.getByLabel("Password")).toBeVisible();
    await expect(page.getByRole("button", { name: "Log in" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Register" })).toBeVisible();
  });

  test("logs in with valid credentials and lands on the app", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill(E2E_USER.email);
    await page.getByLabel("Password").fill(E2E_USER.password);
    await page.getByRole("button", { name: "Log in" }).click();

    // The e2e user was registered by global-setup, so login succeeds and the
    // route guard lets us through to the landing page ("New Canvas" button).
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("button", { name: "New Canvas" })).toBeVisible({ timeout: 10_000 });
  });

  test("shows an inline error for invalid credentials", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill(E2E_USER.email);
    await page.getByLabel("Password").fill("wrong-password");
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
    await expect(page.getByLabel("Password")).toBeVisible();
    await expect(page.getByLabel("Confirm password")).toBeVisible();
    await expect(page.getByRole("button", { name: "Create account" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Log in" })).toBeVisible();
  });

  test("registers a new account and lands on the app", async ({ page }) => {
    const uniqueEmail = `e2e-register-${Date.now()}@agentgraphstudio.test`;
    await page.goto("/register");
    await page.getByLabel("Email").fill(uniqueEmail);
    await page.getByLabel("Password").fill(E2E_USER.password);
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