const { test, expect } = require("@playwright/test");

const pixel = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z9WQAAAAASUVORK5CYII=",
  "base64",
);

test("image recognition results are processed explicitly as SMILES", async ({ page }) => {
  let processRequest;

  await page.route("**/api/parse-image", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ success: true, smiles: "CO", source: "DECIMER" }),
    });
  });

  await page.route("**/api/process", async (route) => {
    processRequest = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        status: "partial",
        smiles: "CO",
        source: "SMILES",
        input_type: "smiles",
        image_2d_base64: null,
        pdb_data: null,
        molecule_info: { formula: "CH4O" },
        validation: { valid: true, issues: [], warnings: [] },
        stages: {
          parse: { success: true, error: null },
          render_2d: { success: false, error: "not rendered in test" },
          render_3d: { success: false, error: "not rendered in test" },
          molecule_info: { success: true, error: null },
          validation: { success: true, error: null },
        },
      }),
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: /图像识别/ }).click();
  await page.locator("#image-input").setInputFiles({
    name: "methanol.png",
    mimeType: "image/png",
    buffer: pixel,
  });
  await page.locator("#btn-parse-image").click();

  await expect(page.locator("#result-section")).toBeVisible();
  expect(processRequest).toEqual({ input: "CO", input_type: "smiles" });
});
