import React from "react";
import { Text, Box } from "ink";

export interface ToolRow {
  name: string;
  found: boolean;
  version: string | null;
  required: boolean;
}

interface ToolTableProps {
  tools: ToolRow[];
}

export function ToolTable({ tools }: ToolTableProps): React.ReactElement {
  if (tools.length === 0) return <></>;

  const nameW = Math.max(...tools.map((t) => t.name.length), 8) + 2;
  const statusW = 14;
  const verW = Math.max(...tools.map((t) => (t.version || "---").length), 9) + 2;

  return (
    <Box flexDirection="column">
      <Text bold>
        {"  "}
        {"Tool".padEnd(nameW)}
        {"Status".padEnd(statusW)}
        {"Version".padEnd(verW)}
      </Text>
      <Text dimColor>
        {"  "}
        {"─".repeat(nameW + statusW + verW + 10)}
      </Text>
      {tools.map((tool) => (
        <Box key={tool.name}>
          <Text>{"  "}{tool.name.padEnd(nameW)}</Text>
          {tool.found ? (
            <Text color="green">{"found".padEnd(statusW)}</Text>
          ) : tool.required ? (
            <Text color="red">{"missing".padEnd(statusW)}</Text>
          ) : (
            <Text dimColor>{"not found".padEnd(statusW)}</Text>
          )}
          <Text>{(tool.version || "---").padEnd(verW)}</Text>
          {tool.required ? (
            <Text dimColor>required</Text>
          ) : (
            <Text dimColor>optional</Text>
          )}
        </Box>
      ))}
    </Box>
  );
}
