import React, { useState } from "react";
import { Text, Box } from "ink";
import TextInput from "ink-text-input";
import { userInfo } from "os";
import { saveState } from "../utils/state.js";
import type { StepProps } from "../types.js";

export function AboutYou({ state, setState, onNext }: StepProps): React.ReactElement {
  const defaultName = state.user_name || userInfo().username;
  const [name, setName] = useState(defaultName);
  const [submitted, setSubmitted] = useState(false);

  if (submitted) {
    return (
      <Box flexDirection="column">
        <Text>
          {"  "}Hi, <Text bold color="green">{state.user_name}</Text>!
        </Text>
      </Box>
    );
  }

  return (
    <Box flexDirection="column">
      <Text>What should we call you?</Text>
      <Box marginTop={1}>
        <Text>{"  > "}</Text>
        <TextInput
          value={name}
          onChange={setName}
          onSubmit={(val) => {
            const finalName = val.trim() || defaultName;
            setState((prev) => {
              const next = {
                ...prev,
                user_name: finalName,
                completed_step_id: "about-you" as const,
              };
              return next;
            });
            saveState({ ...state, user_name: finalName, completed_step_id: "about-you" });
            setSubmitted(true);
            setTimeout(onNext, 300);
          }}
        />
      </Box>
      <Text dimColor>{"  "}Press enter to confirm (default: {defaultName})</Text>
    </Box>
  );
}
