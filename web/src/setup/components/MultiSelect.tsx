import React, { useState } from "react";
import { Text, Box, useInput } from "ink";

interface MultiSelectItem {
  label: string;
  value: string;
}

interface MultiSelectProps {
  items: MultiSelectItem[];
  onSubmit: (selected: string[]) => void;
}

export function MultiSelect({
  items,
  onSubmit,
}: MultiSelectProps): React.ReactElement {
  const [cursor, setCursor] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // items + "Select all" + "Select none" = items.length + 2
  const totalRows = items.length + 2;

  useInput((input, key) => {
    if (key.upArrow) {
      setCursor((c) => (c > 0 ? c - 1 : totalRows - 1));
    } else if (key.downArrow) {
      setCursor((c) => (c < totalRows - 1 ? c + 1 : 0));
    } else if (input === " ") {
      if (cursor < items.length) {
        setSelected((prev) => {
          const next = new Set(prev);
          const val = items[cursor].value;
          if (next.has(val)) next.delete(val);
          else next.add(val);
          return next;
        });
      } else if (cursor === items.length) {
        setSelected(new Set(items.map((i) => i.value)));
      } else {
        setSelected(new Set());
      }
    } else if (key.return) {
      onSubmit(Array.from(selected));
    }
  });

  return (
    <Box flexDirection="column">
      {items.map((item, i) => (
        <Text key={item.value}>
          {cursor === i ? ">" : " "} {selected.has(item.value) ? "[x]" : "[ ]"}{" "}
          {i + 1}. {item.label}
        </Text>
      ))}
      <Text> </Text>
      <Text>
        {cursor === items.length ? ">" : " "} Select all
      </Text>
      <Text>
        {cursor === items.length + 1 ? ">" : " "} Select none
      </Text>
      <Text dimColor>
        {"  "}up/down move | space toggle | enter confirm
      </Text>
    </Box>
  );
}
