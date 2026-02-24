import React from 'react';
import { A2UIComponentProps, resolveBoundValue } from '../types';
import { Badge } from '../../chat/ui/Badge';

export const A2UIBadge: React.FC<A2UIComponentProps> = ({ def, dataModel }) => {
  const text = resolveBoundValue(def.text, dataModel);
  const style = def.style || 'default'; // default, secondary, destructive, outline
  
  if (!text) return null;

  let variant: "default" | "secondary" | "destructive" | "outline" = "default";
  if (style === 'secondary') variant = 'secondary';
  if (style === 'danger' || style === 'destructive') variant = 'destructive';
  if (style === 'outline') variant = 'outline';

  return <Badge variant={variant}>{text}</Badge>;
};
