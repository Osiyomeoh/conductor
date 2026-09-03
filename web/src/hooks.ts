import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { State } from "./types";

// Polls /api/state and exposes typed actions. The 4s poll pauses while an
// overlay is open so a drill-in view is not yanked out from under the reader.
export function useConductor(paused: boolean) {
  const [state, setState] = useState<State | null>(null);
  const timer = useRef<number | null>(null);

  const load = useCallback(async () => {
    try { setState(await api.state()); } catch { /* transient */ }
  }, []);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (paused) return;
    timer.current = window.setInterval(() => void load(), 4000);
    return () => { if (timer.current) window.clearInterval(timer.current); };
  }, [paused, load]);

  const tick = useCallback(async (n: number) => setState(await api.tick(n)), []);
  const answer = useCallback(
    async (id: string, choice: string) => setState(await api.answer(id, choice)), []);

  return { state, tick, answer, reload: load };
}

const KEY = "conductor-theme";
export function useTheme(): [boolean, () => void] {
  const [dark, setDark] = useState<boolean>(() => {
    try {
      const s = localStorage.getItem(KEY);
      return s ? s === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    } catch { return true; }
  });
  useEffect(() => {
    document.documentElement.classList.toggle("dk", dark);
    try { localStorage.setItem(KEY, dark ? "dark" : "light"); } catch { /* ignore */ }
  }, [dark]);
  return [dark, () => setDark((d) => !d)];
}

// Count-up on a changing number, so the hero figures animate like the vanilla app.
export function useCount(to: number): number {
  const [v, setV] = useState(to);
  const from = useRef(to);
  useEffect(() => {
    const start = performance.now(), dur = 460, a = from.current, b = to;
    if (a === b) return;
    let raf = 0;
    const step = (now: number) => {
      const p = Math.min(1, (now - start) / dur);
      setV(Math.round(a + (b - a) * (1 - Math.pow(1 - p, 3))));
      if (p < 1) raf = requestAnimationFrame(step); else from.current = b;
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [to]);
  return v;
}
