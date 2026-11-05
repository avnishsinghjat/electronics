import { ADMIN, adminApi, expect, test } from "./fixtures";

test.describe("authentication", () => {
  test.use({ loginAs: null });

  test("login, logout, and protected pages redirect to login", async ({ page }) => {
    await page.goto("/settings/users");
    await expect(page).toHaveURL(/\/login\?next=%2Fsettings%2Fusers$/);
    await page.getByLabel("Username").fill(ADMIN.username);
    await page.getByLabel("Password").fill(ADMIN.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/settings\/users$/);
    await expect(page.getByRole("cell", { name: ADMIN.username, exact: true })).toBeVisible();

    // A reload keeps the session (refresh cookie), without signing in again.
    await page.reload();
    await expect(page.getByRole("button", { name: new RegExp(`Account menu.*${ADMIN.fullName}`) })).toBeVisible();

    await page.getByRole("button", { name: new RegExp(`Account menu.*${ADMIN.fullName}`) }).click();
    await page.getByRole("menuitem", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login$/);
    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  });
});

test("wrong password shows an error, five failures lock the account", async ({ page, browser }) => {
  const admin = await adminApi(page);
  await admin.createUser("e2e_lockout", ["viewer"]);
  const anon = await browser.newPage();
  await anon.goto("/login");
  for (let i = 1; i <= 4; i++) {
    await anon.getByLabel("Username").fill("e2e_lockout");
    await anon.getByLabel("Password").fill(`wrong-password-${i}`);
    await anon.getByRole("button", { name: "Sign in" }).click();
    await expect(anon.getByRole("alert")).toHaveText("Invalid username or password");
  }
  await anon.getByLabel("Password").fill("wrong-password-5");
  await anon.getByRole("button", { name: "Sign in" }).click();
  await expect(anon.getByRole("alert")).toContainText("Account locked for 15 minutes");
  await anon.close();
});

test("new user must replace the temporary password, then lands on their start page", async ({ page, browser }) => {
  const admin = await adminApi(page);
  const { temporary_password } = await admin.createUser("e2e_stores", ["stores"]);

  const fresh = await browser.newPage();
  await fresh.goto("/login");
  await fresh.getByLabel("Username").fill("e2e_stores");
  await fresh.getByLabel("Password").fill(temporary_password);
  await fresh.getByRole("button", { name: "Sign in" }).click();
  await expect(fresh.getByRole("heading", { name: "Choose a new password" })).toBeVisible();

  // Every other page is blocked until the password is changed.
  await fresh.goto("/settings");
  await expect(fresh).toHaveURL(/\/change-password$/);

  await fresh.getByLabel("Temporary password").fill(temporary_password);
  await fresh.getByLabel("New password", { exact: true }).fill("Stores-own-pass-26");
  await fresh.getByLabel("Confirm new password").fill("Stores-own-pass-26");
  await fresh.getByRole("button", { name: "Change password" }).click();
  await expect(fresh.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
  // Stores has no Settings access: the item is not in the sidebar.
  await expect(fresh.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Settings" })).toHaveCount(0);
  await fresh.close();
});
