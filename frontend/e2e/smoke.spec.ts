// Smoke test for a running copy of the app: the Docker image in CI, or the deployed URL (BASE_URL).
// It checks what a desk user relies on, against the committed January 2026 snapshot.

import { expect, test, type Page } from "@playwright/test";

function watchErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(String(error)));
  return errors;
}

const hero = (page: Page) => page.getByRole("heading", { level: 2, name: /Bidding at/ });

test("the API is up and serves the January snapshot", async ({ request }) => {
  const health = await request.get("/api/health");
  expect(health.ok()).toBe(true);
  expect(await health.json()).toMatchObject({ status: "ok" });

  const meta = await request.get("/api/v1/meta");
  expect(meta.ok()).toBe(true);
  expect(meta.headers()["etag"]).toBeTruthy();
  const body = (await meta.json()) as { delivery_days: string[]; default_cutoff_uk: string };
  expect(body.delivery_days).toHaveLength(31);
  expect(body.default_cutoff_uk).toBe("09:00");

  const bad = await request.get("/api/v1/accuracy?cutoff=17:00");
  expect(bad.status()).toBe(422);
});

test("opens on the day view at the 09:00 cutoff with the 07:30 run", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/");
  await expect(page).toHaveTitle(/Wind at cutoff/);
  await expect(hero(page)).toHaveAccessibleName(/Bidding at 09:00 with the 07:30 forecast/);
  await expect(page.getByRole("heading", { name: /2 January 2026/ })).toBeVisible();
  await expect(page.getByRole("figure", { name: "Forecast at the cutoff vs outturn" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("the cutoff moves with the keyboard and the run follows the rule", async ({ page }) => {
  await page.goto("/");
  await expect(hero(page)).toHaveAccessibleName(/09:00 with the 07:30/);
  const slider = page.getByRole("slider", { name: /Decision cutoff/ });
  await slider.focus();
  for (let i = 0; i < 6; i += 1) await page.keyboard.press("ArrowRight");
  await expect(hero(page)).toHaveAccessibleName(/Bidding at 12:00 with the 11:30 forecast/);
  await expect(page).toHaveURL(/cutoff=12%3A00/);
});

test("a missing run falls back to the previous one", async ({ page }) => {
  await page.goto("/?day=2026-01-16&cutoff=12:00");
  await expect(hero(page)).toHaveAccessibleName(/12:00 with the 09:30 forecast/);
  await expect(page.getByText(/falls back to the 09:30 run/)).toBeVisible();
});

test("the error view leads with the buffer", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Error and buffer" }).click();
  await expect(page.getByText("Hold above the forecast")).toBeVisible();
  await expect(page.locator(".hero-number")).toHaveText(/^\d{1,2},\d{3} MW$/);
  await page.getByRole("radio", { name: "95%" }).check();
  await expect(page).toHaveURL(/coverage=95/);
  await expect(page.getByRole("figure", { name: "Error by lead time and hour of day, every forecast run" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("the page fits the screen without sideways scrolling", async ({ page }) => {
  for (const path of ["/", "/?view=error"]) {
    await page.goto(path);
    await expect(hero(page)).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, path).toBeLessThanOrEqual(0);
  }
});
