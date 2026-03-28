import React from 'react';
import { A2UIComponentProps, resolveBoundValue } from '../types';
import { Input } from '../../chat/ui/Input';

export const A2UITextField: React.FC<A2UIComponentProps> = ({ def, dataModel, updateField, completed }) => {
  const label = resolveBoundValue(def.label, dataModel);
  const placeholder = resolveBoundValue(def.placeholder, dataModel) || '';

  // Data binding
  const path = def.text?.path;
  const value = path ? resolveBoundValue(def.text, dataModel) : (def.text?.literalString || '');

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (path && updateField) {
      updateField(path, e.target.value);
    }
  };

  return (
    <div className="flex flex-col gap-1.5 w-full">
      {label && <label className="text-sm font-medium text-foreground">{label}</label>}
      <Input
        type={def.password ? "password" : "text"}
        value={value}
        onChange={handleChange}
        placeholder={placeholder}
        disabled={completed || def.disabled}
        className="w-full"
      />
    </div>
  );
};
