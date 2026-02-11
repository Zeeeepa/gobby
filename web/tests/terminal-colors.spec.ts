import { test } from "@playwright/test";

// ANSI color lines to inject into the mock terminal
const ANSI_OUTPUT = [
  "\x1b[1;37m=== ANSI Color Test ===\x1b[0m",
  "",
  "\x1b[30m[30] ANSI Black\x1b[0m  <-- should be visible",
  "\x1b[31m[31] Red\x1b[0m",
  "\x1b[32m[32] Green\x1b[0m",
  "\x1b[33m[33] Yellow\x1b[0m",
  "\x1b[34m[34] Blue\x1b[0m",
  "\x1b[35m[35] Magenta\x1b[0m",
  "\x1b[36m[36] Cyan\x1b[0m",
  "\x1b[37m[37] White\x1b[0m",
  "\x1b[90m[90] Bright Black\x1b[0m",
  "",
  "Default foreground text for comparison",
].join("\r\n") + "\r\n";

const MOCK_SESSIONS = [
  {
    name: "test-session",
    socket: "default",
    windows: 1,
    created: new Date().toISOString(),
    attached: false,
    agent_managed: false,
    pane_pid: 12345,
    pane_current_command: "zsh",
  },
];

const STREAMING_ID = "mock-stream-001";

test("screenshot terminal ANSI colors", async ({ page }) => {
  // Mock the WebSocket to provide fake tmux sessions and ANSI output
  await page.routeWebSocket("**/ws", (ws) => {
    ws.onMessage((msg) => {
      const data = JSON.parse(msg as string);

      switch (data.type) {
        case "subscribe":
          // Acknowledge subscription silently
          break;

        case "tmux_list_sessions":
          ws.send(
            JSON.stringify({
              type: "tmux_sessions_list",
              sessions: MOCK_SESSIONS,
            })
          );
          break;

        case "tmux_attach":
          ws.send(
            JSON.stringify({
              type: "tmux_attach_result",
              success: true,
              streaming_id: STREAMING_ID,
              session_name: data.session_name,
            })
          );
          // Send ANSI color output shortly after attach
          setTimeout(() => {
            ws.send(
              JSON.stringify({
                type: "terminal_output",
                run_id: STREAMING_ID,
                data: ANSI_OUTPUT,
              })
            );
          }, 200);
          break;

        case "tmux_detach":
          ws.send(
            JSON.stringify({
              type: "tmux_detach_result",
              success: true,
            })
          );
          ws.send(
            JSON.stringify({
              type: "tmux_sessions_list",
              sessions: MOCK_SESSIONS,
            })
          );
          break;

        case "terminal_input":
          break;

        case "tmux_resize":
          break;
      }
    });
  });

  // Mock HTTP endpoints to prevent 404 noise
  await page.route("**/tasks*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ tasks: [], total: 0, stats: {}, limit: 200, offset: 0 }),
    })
  );
  await page.route("**/sessions*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ sessions: [], total: 0 }),
    })
  );

  await page.goto("/");

  // Navigate to Terminals page
  await page.click(".hamburger-button");
  await page.click("text=Terminals");
  await page.waitForSelector(".terminals-page");

  // Wait for mock session to appear and attach
  await page.locator(".session-item-main").first().waitFor();
  await page.locator(".session-item-main").first().click();

  // Wait for xterm DOM renderer to render rows (v6 uses DOM, not canvas)
  await page.waitForSelector(".xterm-screen", { timeout: 10000 });
  await page.locator(".xterm-rows").waitFor({ timeout: 5000 });

  // Wait for ANSI output to appear in the terminal
  await page.locator(".xterm-rows").getByText("Default foreground text").waitFor({ timeout: 5000 });

  await page.screenshot({
    path: "tests/screenshots/terminal-colors.png",
    fullPage: true,
  });
});
