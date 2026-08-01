import { expect, test } from "@playwright/test";

test("tenant A sees only its server-derived case and no browser tokens", async ({ page }) => {
  await page.goto("/cases");
  await expect(page.locator(".identity")).toContainText("tenant-a-reviewer");
  await expect(page.locator(".case-card")).toContainText("tenant-a quote");
  await expect(page.locator(".case-card")).not.toContainText("tenant-b");
  await page.locator(".case-card").click();
  await expect(page.getByText("Governance outcome: REVIEW")).toBeVisible();
  await expect(page.getByRole("button", { name: "Request deletion" })).toBeVisible();
  await expect(page.locator("img")).toHaveCount(0);
  expect(await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length, cookies: document.cookie }))).toEqual({ local: 0, session: 0, cookies: "" });
});

test("tenant B cannot enumerate or directly read tenant A", async ({ page }) => {
  await page.goto("/test/tenant-b");
  await expect(page.locator(".identity")).toContainText("tenant-b-reviewer");
  await expect(page.locator(".case-card")).toContainText("tenant-b quote");
  await expect(page.locator(".case-card")).not.toContainText("tenant-a");
  const result = await page.evaluate(async () => {
    const response = await fetch("/bff/api/v1/decisions/tenant-a-quote");
    return { status: response.status, body: await response.json() };
  });
  expect(result).toEqual({ status: 404, body: { code: "NOT_FOUND", correlation_id: "browser-e2e-correlation" } });
});
