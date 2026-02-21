import type { SetupState } from "./utils/state.js";

/** Props passed to every wizard step component. */
export interface StepProps {
  state: SetupState;
  setState: (fn: (prev: SetupState) => SetupState) => void;
  onNext: () => void;
}
