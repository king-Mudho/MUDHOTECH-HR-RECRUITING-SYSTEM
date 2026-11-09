"use client";

import { useEffect, useRef } from "react";

/**
 * Debounced autosave: calls `save` `delay` ms after `value` stops changing, only while `enabled`
 * (form dirty + client-valid). The serialised value is compared so re-renders do not re-save.
 */
export function useAutosave<T>(value: T, enabled: boolean, save: () => void, delay = 1500): void {
  const serialised = JSON.stringify(value);
  const last = useRef(serialised);
  const saveRef = useRef(save);
  useEffect(() => {
    saveRef.current = save;
  });
  useEffect(() => {
    if (!enabled || serialised === last.current) return;
    const id = setTimeout(() => {
      last.current = serialised;
      saveRef.current();
    }, delay);
    return () => clearTimeout(id);
  }, [serialised, enabled, delay]);
}
