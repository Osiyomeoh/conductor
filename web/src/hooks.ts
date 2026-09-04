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

// Voice dictation via the browser's Web Speech API. No key, no backend: the
// browser transcribes and we append each finalized phrase. Unsupported browsers
// (notably Firefox) report supported=false, and the caller hides the control.
type SR = { lang: string; interimResults: boolean; continuous: boolean;
  onresult: ((e: unknown) => void) | null; onend: (() => void) | null;
  onerror: (() => void) | null; start: () => void; stop: () => void };

export function useDictation(onPhrase: (text: string) => void, onInterim?: (text: string) => void) {
  const [listening, setListening] = useState(false);
  const rec = useRef<SR | null>(null);
  const supported = typeof window !== "undefined" &&
    ("SpeechRecognition" in window || "webkitSpeechRecognition" in window);

  const stop = useCallback(() => { try { rec.current?.stop(); } catch { /* */ } setListening(false); }, []);

  const start = useCallback(() => {
    if (!supported) return;
    const Ctor = (window as unknown as Record<string, new () => SR>).SpeechRecognition
      || (window as unknown as Record<string, new () => SR>).webkitSpeechRecognition;
    const r = new Ctor();
    r.lang = "en-US"; r.interimResults = true; r.continuous = true;
    r.onresult = (e: unknown) => {
      const ev = e as { resultIndex: number; results: ArrayLike<{ 0: { transcript: string }; isFinal: boolean }> };
      let final = "", interim = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const seg = ev.results[i][0].transcript;
        if (ev.results[i].isFinal) final += seg; else interim += seg;
      }
      if (final) onPhrase(final.trim());
      if (interim && onInterim) onInterim(interim.trim());
    };
    r.onend = () => setListening(false);
    r.onerror = () => setListening(false);
    try { r.start(); rec.current = r; setListening(true); } catch { setListening(false); }
  }, [supported, onPhrase, onInterim]);

  useEffect(() => () => { try { rec.current?.stop(); } catch { /* */ } }, []);
  return { supported, listening, start, stop };
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
