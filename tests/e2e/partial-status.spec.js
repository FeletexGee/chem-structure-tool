const { test, expect } = require("@playwright/test");

const pixel = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z9WQAAAAASUVORK5CYII=";

test("a partial result clears stale rendered state", async ({ page }) => {
  let callCount = 0;
  await page.route("**/api/process", async (route) => {
    callCount += 1;
    const partial = callCount === 2;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        status: partial ? "partial" : "resolved",
        smiles: partial ? "CCN" : "CCO",
        source: "SMILES",
        input_type: "smiles",
        image_2d_base64: pixel,
        pdb_data: null,
        molecule_info: { formula: partial ? "C2H7N" : "C2H6O" },
        validation: { valid: true, issues: [], warnings: [] },
        stages: {
          parse: { success: true, error: null },
          render_2d: { success: true, error: null },
          render_3d: partial
            ? { success: false, error: "3D 构象生成失败" }
            : { success: true, error: null },
          molecule_info: { success: true, error: null },
          validation: { success: true, error: null },
        },
      }),
    });
  });

  await page.goto("/");
  await page.locator("#text-input").fill("first");
  await page.locator("#btn-parse-text").click();
  await expect(page.locator("#result-section")).toBeVisible();

  await page.locator("#viewer-3d").evaluate((element) => {
    element.innerHTML = '<span id="stale-model-marker">old model</span>';
  });

  await page.locator("#text-input").fill("second");
  await page.locator("#btn-parse-text").click();

  await expect(page.locator("#stale-model-marker")).toHaveCount(0);
  await expect(page.locator("#render-3d-status")).toContainText("3D 构象生成失败");
});
