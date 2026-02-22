import React from "react";
import { Text, Box } from "ink";

interface StepHeaderProps {
  stepNumber: number;
  totalSteps: number;
  title: string;
}

export function StepHeader({
  stepNumber,
  totalSteps,
  title,
}: StepHeaderProps): React.ReactElement {
  return (
    <Box marginTop={1} marginBottom={1}>
      <Text bold color="blue">
        Step {stepNumber}/{totalSteps}: {title}
      </Text>
    </Box>
  );
}
