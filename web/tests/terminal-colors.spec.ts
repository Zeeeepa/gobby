import { test } from "@playwright/test";

test("screenshot terminal ANSI colors", async ({ page }) => {
  await page.goto("/");
  await page.click("text=Terminals");
  await page.waitForSelector(".terminals-page");
  await page.waitForTimeout(2000);

  // Attach to first session
  await page.locator(".session-item-main").first().click();
  await page.waitForSelector(".xterm-screen", { timeout: 10000 });
  await page.waitForTimeout(1000);

  // Detach to force re-creation of xterm with current theme
  await page.click("text=Detach");
  await page.waitForTimeout(500);

  // Re-attach
  await page.locator(".session-item-main").first().click();
  await page.waitForSelector(".xterm-screen", { timeout: 10000 });
  await page.waitForTimeout(1500);

  // Focus and type
  await page.locator(".terminals-terminal-content").click();
  await page.waitForTimeout(300);

  await page.keyboard.type("clear", { delay: 20 });
  await page.keyboard.press("Enter");
  await page.waitForTimeout(500);

  // Simpler: use a here-document approach with /bin/echo or just $'...'
  const commands = [
    `echo $'\\e[1;37m=== ANSI Color Test ===\\e[0m'`,
    `echo ''`,
    `echo $'\\e[30m[30] ANSI Black\\e[0m  <-- should be visible'`,
    `echo $'\\e[31m[31] Red\\e[0m'`,
    `echo $'\\e[32m[32] Green\\e[0m'`,
    `echo $'\\e[33m[33] Yellow\\e[0m'`,
    `echo $'\\e[34m[34] Blue\\e[0m'`,
    `echo $'\\e[35m[35] Magenta\\e[0m'`,
    `echo $'\\e[36m[36] Cyan\\e[0m'`,
    `echo $'\\e[37m[37] White\\e[0m'`,
    `echo $'\\e[90m[90] Bright Black\\e[0m'`,
    `echo ''`,
    `echo $'Default foreground text for comparison'`,
  ];

  for (const cmd of commands) {
    await page.keyboard.type(cmd, { delay: 3 });
    await page.keyboard.press("Enter");
    await page.waitForTimeout(300);
  }

  await page.waitForTimeout(1500);

  await page.screenshot({
    path: "tests/screenshots/terminal-colors.png",
    fullPage: true,
  });
});
