import React from 'react';
import { A2UIComponentProps, resolveBoundValue } from '../types';

export const A2UICheckBox: React.FC<A2UIComponentProps> = ({ def, dataModel, updateField, completed }) => {
  const label = resolveBoundValue(def.label, dataModel);
  
  // Data binding
  const path = def.checked?.path;
  const checked = path ? resolveBoundValue(def.checked, dataModel) === true : (def.checked?.literalString === 'true');

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (path && updateField) {
      updateField(path, e.target.checked);
    }
  };

  return (
    <div className="flex items-center space-x-2">
      <input
        type="checkbox"
        id={`checkbox-${def.id}`}
        checked={checked}
        onChange={handleChange}
        disabled={completed || def.disabled}
        className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
      />
      {label && (
        <label
          htmlFor={`checkbox-${def.id}`}
          className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
        >
          {label}
        </label>
      )}
    </div>
  );
};
