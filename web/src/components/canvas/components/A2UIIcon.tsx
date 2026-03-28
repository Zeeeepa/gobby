import React from 'react';
import { A2UIComponentProps, resolveBoundValue } from '../types';

const customIcons = {
  check: <path d="M20 6L9 17l-5-5" />,
  x: <path d="M18 6L6 18M6 6l12 12" />,
  alert: <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0zM12 9v4m0 4h.01" />,
  info: <path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10zm0-15v2m0 4v4" />,
  "arrow-right": <path d="M5 12h14m-7-7l7 7-7 7" />,
  help: <path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3m.08 4h.01M12 22A10 10 0 102 12c0 5.523 4.477 10 10 10z" />
};

export const A2UIIcon: React.FC<A2UIComponentProps> = ({ def, dataModel }) => {
  const name = resolveBoundValue(def.name, dataModel);
  const color = def.color || "currentColor";

  const iconPath = customIcons[name as keyof typeof customIcons] || customIcons.help;
  const sizeClass = def.size === 'large' ? 'h-6 w-6' : def.size === 'small' ? 'h-3 w-3' : 'h-4 w-4';

  return (
    <svg className={sizeClass} style={{ color }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      {iconPath}
    </svg>
  );
};
