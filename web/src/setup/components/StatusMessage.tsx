import React from "react";
import { Text } from "ink";

type Level = "success" | "warning" | "error" | "info";

interface StatusMessageProps {
  level: Level;
  children: React.ReactNode;
}

const COLORS: Record<Level, string> = {
  success: "green",
  warning: "yellow",
  error: "red",
  info: "blue",
};

const ICONS: Record<Level, string> = {
  success: "ok",
  warning: "!!",
  error: "XX",
  info: "ii",
};

export function StatusMessage({
  level,
  children,
}: StatusMessageProps): React.ReactElement {
  return (
    <Text color={COLORS[level]}>
      [{ICONS[level]}] {children}
    </Text>
  );
}
