import React from "react";
import { Text, Box } from "ink";

const BANNER = `   ██████   ██████  ██████  ██████  ██    ██
  ██       ██    ██ ██   ██ ██   ██  ██  ██
  ██   ███ ██    ██ ██████  ██████    ████
  ██    ██ ██    ██ ██   ██ ██   ██    ██
   ██████   ██████  ██████  ██████     ██`;

interface BannerProps {
  version?: string;
}

export function Banner({ version }: BannerProps): React.ReactElement {
  return (
    <Box flexDirection="column" alignItems="center">
      <Text color="blue">{BANNER}</Text>
      {version && <Text dimColor>v{version}</Text>}
    </Box>
  );
}
