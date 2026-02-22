import React, { useState, useEffect } from "react";
import { Text, Box } from "ink";
import Spinner from "ink-spinner";
import { exec } from "child_process";
import { isGobbyInstalled } from "../utils/gobby.js";
import { detectTool } from "../utils/detect.js";
import { StatusMessage } from "../components/StatusMessage.js";
import type { StepProps } from "../types.js";

type Phase = "checking" | "need-python" | "need-gobby" | "installing" | "done" | "error";

export function Bootstrap({ onNext }: StepProps): React.ReactElement {
  const [phase, setPhase] = useState<Phase>("checking");
  const [error, setError] = useState("");

  useEffect(() => {
    if (isGobbyInstalled()) {
      setPhase("done");
      return;
    }

    const pyVer = detectTool("python");
    if (!pyVer) {
      setPhase("need-python");
      return;
    }

    const hasUv = detectTool("uv");
    if (!hasUv) {
      setPhase("need-gobby");
      return;
    }

    setPhase("installing");
  }, []);

  // Run install asynchronously so the spinner can render
  useEffect(() => {
    if (phase !== "installing") return;

    const child = exec("uv tool install gobby", { encoding: "utf-8", timeout: 120000 }, (err) => {
      if (err) {
        setError(err.message);
        setPhase("error");
        return;
      }
      if (isGobbyInstalled()) {
        setPhase("done");
      } else {
        setError("Installation completed but gobby not found in PATH");
        setPhase("error");
      }
    });

    return () => { child.kill(); };
  }, [phase]);

  useEffect(() => {
    if (phase === "done") {
      const timer = setTimeout(onNext, 500);
      return () => clearTimeout(timer);
    }
  }, [phase, onNext]);

  if (phase === "checking") {
    return (
      <Text>
        <Spinner type="dots" /> Checking for Gobby installation...
      </Text>
    );
  }

  if (phase === "need-python") {
    return (
      <Box flexDirection="column">
        <StatusMessage level="error">
          Python 3.13+ is required but not found.
        </StatusMessage>
        <Text> </Text>
        {process.platform === "darwin" ? (
          <Text>
            {"  "}Install: <Text bold>brew install python@3.13</Text>
          </Text>
        ) : (
          <Text>
            {"  "}Install: <Text bold>sudo apt install python3.13</Text> or
            visit https://python.org
          </Text>
        )}
        <Text dimColor>{"  "}Then re-run: npx @gobby/setup</Text>
      </Box>
    );
  }

  if (phase === "need-gobby") {
    return (
      <Box flexDirection="column">
        <StatusMessage level="warning">
          Gobby is not installed and uv is required to auto-install.
        </StatusMessage>
        <Text>
          {"  "}Install uv:{" "}
          <Text bold>curl -LsSf https://astral.sh/uv/install.sh | sh</Text>
        </Text>
        <Text>
          {"  "}Then: <Text bold>uv tool install gobby</Text>
        </Text>
      </Box>
    );
  }

  if (phase === "installing") {
    return (
      <Text>
        <Spinner type="dots" /> Installing Gobby via uv...
      </Text>
    );
  }

  if (phase === "error") {
    return (
      <Box flexDirection="column">
        <StatusMessage level="error">
          Installation failed: {error}
        </StatusMessage>
        <Text dimColor>{"  "}Try manually: uv tool install gobby</Text>
      </Box>
    );
  }

  return <StatusMessage level="success">Gobby is installed.</StatusMessage>;
}
