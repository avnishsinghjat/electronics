import { chromium, type FullConfig } from "@playwright/test";

import { ADMIN } from "./fixtures";

/**
 * Runs once after the web servers start. On a fresh database it completes the first-run
 * setup wizard through the real UI (so the wizard itself is exercised end to end).
 */
export default async function globalSetup(config: FullConfig): Promise<void> {
  const baseURL = config.projects[0]?.use.baseURL ?? "http://127.0.0.1:4173";
  const browser = await chromium.launch();
  const page = await browser.newPage({ baseURL });
  try {
    const status = await (await page.request.get("/api/setup/status")).json();
    if (!status.needs_setup) return;
    await page.goto("/");
    await page.getByRole("heading", { name: "Set up FabTrack" }).waitFor();
    await page.getByText("Data directory is ready").waitFor();
    await page.getByRole("button", { name: /Continue/ }).click();
    await page.getByLabel(/Company name/).fill("Sahyadri Electronics (E2E)");
    await page.getByLabel("Administrator username").fill(ADMIN.username);
    await page.getByLabel("Administrator full name").fill(ADMIN.fullName);
    await page.getByLabel(/^Password/).fill(ADMIN.password);
    await page.getByLabel("Confirm password").fill(ADMIN.password);
    await page.getByRole("button", { name: /Continue/ }).click();
    await page.getByRole("button", { name: "Create company and administrator" }).click();
    await page.getByText("Setup is complete and you are signed in").waitFor();
    await page.getByRole("button", { name: "Skip for now" }).click();
    await page.getByRole("heading", { level: 1, name: "Dashboard" }).waitFor();
  } finally {
    await browser.close();
  }
}
