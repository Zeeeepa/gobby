import React from 'react';
import { A2UIComponentProps } from '../types';
import { RenderChildren } from '../A2UIRenderer';

export const A2UIRow: React.FC<A2UIComponentProps> = ({ def, surface, dataModel, onAction, updateField, completed, depth }) => {
  return (
    <div className="flex flex-row gap-2 items-center flex-wrap">
      <RenderChildren
        childrenSpec={def.children}
        surface={surface}
        dataModel={dataModel}
        onAction={onAction}
        updateField={updateField}
        completed={completed}
        depth={depth}
      />
    </div>
  );
};
