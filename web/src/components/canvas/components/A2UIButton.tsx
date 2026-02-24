import React from 'react';
import { A2UIComponentProps, resolveBoundValue, resolveActionContext } from '../types';
import { Button } from '../../chat/ui/Button';

export const A2UIButton: React.FC<A2UIComponentProps> = ({ def, componentId, dataModel, onAction, completed }) => {
  const label = resolveBoundValue(def.label, dataModel) || 'Button';
  const style = def.style || 'secondary'; // primary, secondary, danger
  const disabled = completed || def.disabled;
  
  // Map A2UI style to chat UI variant
  let variant: "default" | "destructive" | "outline" | "secondary" | "ghost" | "link" = "secondary";
  if (style === 'primary') variant = 'default';
  if (style === 'danger') variant = 'destructive';

  const handleClick = () => {
    if (def.actions && def.actions.length > 0) {
      const actionDef = def.actions[0];
      const context = resolveActionContext(actionDef.context, dataModel);
      onAction({
        name: actionDef.name,
        sourceComponentId: componentId,
        timestamp: new Date().toISOString(),
        context
      });
    }
  };

  return (
    <Button 
      variant={variant} 
      onClick={handleClick} 
      disabled={disabled}
      className="w-full sm:w-auto"
    >
      {label}
    </Button>
  );
};
