import type { Severity } from "../api/types";

let ctx: AudioContext | null = null;

/** Short synthesized alarm tone (no audio assets). Critical alerts get a triple beep. */
export function playAlertTone(severity: Severity) {
  try {
    ctx ??= new AudioContext();
    const beeps = severity === "CRITICAL" ? 3 : severity === "HIGH" ? 2 : 1;
    const freq = severity === "CRITICAL" || severity === "HIGH" ? 880 : 660;
    for (let i = 0; i < beeps; i++) {
      const t = ctx.currentTime + i * 0.22;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "square";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, t);
      gain.gain.exponentialRampToValueAtTime(0.08, t + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.16);
      osc.connect(gain).connect(ctx.destination);
      osc.start(t);
      osc.stop(t + 0.18);
    }
  } catch {
    /* autoplay restrictions: ignore */
  }
}
