import { readFileSync, writeFileSync, mkdirSync } from "fs";
import { join } from "path";
import { parse, stringify } from "yaml";
import { getGobbyHome } from "./state.js";

function configPath(): string {
  return join(getGobbyHome(), "config.yaml");
}

export function readConfig(): Record<string, unknown> {
  try {
    const raw = readFileSync(configPath(), "utf-8");
    return (parse(raw) as Record<string, unknown>) || {};
  } catch (e: unknown) {
    if (e && typeof e === "object" && "code" in e && (e as { code: string }).code !== "ENOENT") {
      console.error("Failed to read config:", e);
    }
    return {};
  }
}

export function writeConfig(data: Record<string, unknown>): void {
  const dir = getGobbyHome();
  mkdirSync(dir, { recursive: true });
  writeFileSync(configPath(), stringify(data), { mode: 0o600 });
}

export function patchPorts(
  httpPort: number,
  wsPort: number,
  uiPort: number,
): void {
  const data = readConfig() as Record<string, Record<string, unknown>>;
  if (!data.daemon) data.daemon = {};
  data.daemon.port = httpPort;
  if (!data.websocket) data.websocket = {};
  data.websocket.port = wsPort;
  if (!data.ui) data.ui = {};
  data.ui.port = uiPort;
  writeConfig(data);
}

export function setBindHost(host: string): void {
  const data = readConfig();
  data.bind_host = host;
  writeConfig(data);
}
