import React from 'react';
import { A2UIComponentProps, resolveBoundValue } from '../types';
import { Check, X, AlertTriangle, Info, ArrowRight, HelpCircle } from 'lucide-react';

export const A2UIIcon: React.FC<A2UIComponentProps> = ({ def, dataModel }) => {
  const name = resolveBoundValue(def.name, dataModel);
  const color = def.color || "currentColor";
  
  let IconCmp = HelpCircle;
  switch (name) {
    case 'check': IconCmp = Check; break;
    case 'x': IconCmp = X; break;
    case 'alert': IconCmp = AlertTriangle; break;
    case 'info': IconCmp = Info; break;
    case 'arrow-right': IconCmp = ArrowRight; break;
  }
  
  const sizeClass = def.size === 'large' ? 'h-6 w-6' : def.size === 'small' ? 'h-3 w-3' : 'h-4 w-4';

  return <IconCmp className={sizeClass} style={{ color }} />;
};
