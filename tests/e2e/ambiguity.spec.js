const { test, expect } = require("@playwright/test");

test("CO requires an explicit interpretation", async ({ page }) => {
  await page.goto("/");
  await page.locator("#text-input").fill("CO");
  await page.locator("#btn-parse-text").click();

  await expect(page.locator("#ambiguity-panel")).toBeVisible();
  await expect(page.locator("#ambiguity-candidates button")).toHaveCount(2);

  await page.getByRole("button", { name: /按 SMILES 解释/ }).click();

  await expect(page.locator("#result-section")).toBeVisible();
  await expect(page.locator("#text-status")).toContainText("解析成功");
});
