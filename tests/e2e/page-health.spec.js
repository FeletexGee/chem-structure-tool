const { test, expect } = require("@playwright/test");

test("the initial page has no missing static resources", async ({ page }) => {
  const missing = [];
  page.on("response", (response) => {
    if (response.status() === 404) missing.push(response.url());
  });

  await page.goto("/");
  await page.waitForLoadState("networkidle");

  expect(missing).toEqual([]);
});
