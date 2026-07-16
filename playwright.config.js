const { defineConfig, devices } = require("@playwright/test");

const chromiumUse = {
  ...devices["Desktop Chrome"],
  ...(process.platform === "win32" ? { channel: "msedge" } : {}),
};

const mobileUse = {
  ...devices["Pixel 5"],
  ...(process.platform === "win32" ? { channel: "msedge" } : {}),
};

module.exports = defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  use: {
    baseURL: "http://127.0.0.1:5000",
    trace: "retain-on-failure",
  },
  webServer: {
    command: ".venv\\Scripts\\python.exe app.py",
    url: "http://127.0.0.1:5000",
    reuseExistingServer: true,
    timeout: 120_000,
  },
  projects: [
    {
      name: "chromium",
      use: chromiumUse,
    },
    {
      name: "mobile-chromium",
      use: mobileUse,
    },
  ],
});
