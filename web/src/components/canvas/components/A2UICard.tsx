import React from 'react';
import { A2UIComponentProps, resolveBoundValue } from '../types';
import { RenderChildren } from '../A2UIRenderer';

export const A2UICard: React.FC<A2UIComponentProps> = ({ def, surface, dataModel, onAction, completed }) => {
  const label = resolveBoundValue(def.label, dataModel);
  
  return (
    <div className="rounded-lg border border-border p-3 flex flex-col gap-2">
      {label && <div className="font-semibold text-sm">{label}</div>}
      <RenderChildren 
        childrenSpec={def.children} 
        surface={surface} 
        dataModel={dataModel} 
        onAction={onAction} 
        completed={completed} 
      />
    </div>
  );
};
