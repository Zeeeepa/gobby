import React from 'react';
import { A2UIComponentProps } from '../types';
import { RenderChildren } from '../A2UIRenderer';

export const A2UIList: React.FC<A2UIComponentProps> = ({ def, surface, dataModel, onAction, updateField, completed, depth }) => {
  return (
    <ul className="list-disc list-inside space-y-1">
      {def.children?.explicitList?.map((childId) => {
        const childDef = surface[childId];
        if (!childDef) return null;
        return (
          <li key={childId}>
            <RenderChildren
              childrenSpec={{ explicitList: [childId] }}
              surface={surface}
              dataModel={dataModel}
              onAction={onAction}
              updateField={updateField}
              completed={completed}
              depth={depth}
            />
          </li>
        );
      })}
    </ul>
  );
};
