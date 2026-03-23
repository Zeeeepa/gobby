import { useState, useCallback, useEffect } from 'react';

export interface CanvasPanelState {
  canvasId: string;
  title?: string;
  url: string;
  width?: number;
  height?: number;
}

const STORAGE_KEY = 'gobby-canvas-panel-width';

const safeGetItem = (key: string): string | null => {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
};

const safeSetItem = (key: string, value: string): void => {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Storage unavailable (SSR, restricted env, etc.)
  }
};

export const useCanvasPanel = () => {
  const [activeCanvas, setActiveCanvas] = useState<CanvasPanelState | null>(null);
  const [panelWidth, setPanelWidthState] = useState(600);

  useEffect(() => {
    const stored = safeGetItem(STORAGE_KEY);
    if (stored) {
      setPanelWidthState(parseInt(stored, 10));
    }
  }, []);

  const setPanelWidth = useCallback((width: number) => {
    const clamped = Math.max(400, Math.min(1200, width));
    setPanelWidthState(clamped);
    safeSetItem(STORAGE_KEY, clamped.toString());
  }, []);

  const openCanvas = useCallback((state: CanvasPanelState) => {
    setActiveCanvas(state);
  }, []);

  const closeCanvas = useCallback(() => {
    setActiveCanvas(null);
  }, []);

  return {
    activeCanvas,
    isPanelOpen: activeCanvas !== null,
    panelWidth,
    setPanelWidth,
    openCanvas,
    closeCanvas
  };
};
