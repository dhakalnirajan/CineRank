import { useCallback, useEffect, useState } from "react";
import { Volume2, VolumeX } from "lucide-react";
import { CineRankMark } from "../../components/navigation/Logo";

const STORAGE_KEY = "cinerank:intro-seen";
const INTRO_DURATION = 2800;
const REDUCED_MOTION_DURATION = 1100;

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

function hasSeenIntro(): boolean {
  try {
    return window.sessionStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function markIntroSeen(): void {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, "1");
  } catch {
    // Private browsing or disabled storage: the intro still plays once per mount.
  }
}

function useIntroSound(active: boolean) {
  const [muted, setMuted] = useState(false);

  useEffect(() => {
    if (!active || muted) return;
    const AudioCtor: typeof AudioContext | undefined =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext;
    if (!AudioCtor) return;

    const context = new AudioCtor();
    const master = context.createGain();
    master.gain.value = 0.3;
    master.connect(context.destination);
    let cancelled = false;

    const playTone = (
      frequency: number,
      start: number,
      duration: number,
      level: number,
    ) => {
      const now = context.currentTime + 0.08;
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      oscillator.type = "sine";
      oscillator.frequency.setValueAtTime(frequency, now + start);
      gain.gain.setValueAtTime(0.0001, now + start);
      gain.gain.exponentialRampToValueAtTime(level, now + start + 0.06);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + start + duration);
      oscillator.connect(gain);
      gain.connect(master);
      oscillator.start(now + start);
      oscillator.stop(now + start + duration + 0.05);
    };

    const playSweep = () => {
      const now = context.currentTime + 0.08;
      const frames = Math.floor(context.sampleRate * 1.5);
      const buffer = context.createBuffer(1, frames, context.sampleRate);
      const channel = buffer.getChannelData(0);
      for (let index = 0; index < frames; index += 1) {
        channel[index] = Math.random() * 2 - 1;
      }

      const source = context.createBufferSource();
      source.buffer = buffer;

      const filter = context.createBiquadFilter();
      filter.type = "bandpass";
      filter.Q.value = 0.8;
      filter.frequency.setValueAtTime(260, now);
      filter.frequency.exponentialRampToValueAtTime(3200, now + 1.25);

      const gain = context.createGain();
      gain.gain.setValueAtTime(0.0001, now);
      gain.gain.exponentialRampToValueAtTime(0.05, now + 0.45);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 1.5);

      source.connect(filter);
      filter.connect(gain);
      gain.connect(master);
      source.start(now);
      source.stop(now + 1.55);
    };

    let played = false;
    const start = async () => {
      if (cancelled || played) return;
      try {
        if (context.state === "suspended") {
          await context.resume();
        }
      } catch {
        return;
      }
      if (cancelled || played || context.state !== "running") return;
      played = true;
      window.removeEventListener("pointerdown", retryFromGesture);
      window.removeEventListener("keydown", retryFromGesture);
      window.removeEventListener("touchstart", retryFromGesture);
      playSweep();
      playTone(110, 0.15, 1.2, 0.22);
      playTone(220, 0.8, 1.35, 0.15);
      playTone(330, 1.0, 1.1, 0.08);
    };
    const retryFromGesture = () => { void start(); };
    void start();
    window.addEventListener("pointerdown", retryFromGesture, { once: true });
    window.addEventListener("keydown", retryFromGesture, { once: true });
    window.addEventListener("touchstart", retryFromGesture, { once: true, passive: true });

    return () => {
      cancelled = true;
      window.removeEventListener("pointerdown", retryFromGesture);
      window.removeEventListener("keydown", retryFromGesture);
      window.removeEventListener("touchstart", retryFromGesture);
      void context.close().catch(() => undefined);
    };
  }, [active, muted]);

  const toggleMuted = useCallback(() => setMuted((current) => !current), []);
  return { muted, toggleMuted };
}

export function IntroScreen() {
  const [visible, setVisible] = useState(() => !hasSeenIntro());
  const { muted, toggleMuted } = useIntroSound(visible);

  useEffect(() => {
    if (!visible) return;
    const duration = prefersReducedMotion()
      ? REDUCED_MOTION_DURATION
      : INTRO_DURATION;
    const timer = window.setTimeout(() => {
      markIntroSeen();
      setVisible(false);
    }, duration);
    return () => window.clearTimeout(timer);
  }, [visible]);

  if (!visible) return null;

  return (
    <div
      className="intro-screen fixed inset-0 z-[100] flex items-center justify-center overflow-hidden bg-black"
      role="status"
      aria-live="polite"
      aria-label="CineRank is starting"
    >
      <div className="intro-ribbon" aria-hidden="true" />
      <div className="intro-flare" aria-hidden="true" />

      <div className="relative flex flex-col items-center px-6 text-center">
        <div className="intro-mark">
          <CineRankMark className="size-20 sm:size-24" />
        </div>
        <p className="intro-wordmark mt-6 font-display text-3xl font-extrabold tracking-[-0.045em] sm:text-4xl">
          <span className="text-white">Cine</span>
          <span className="text-accent">Rank</span>
        </p>
      </div>

      <button
        type="button"
        onClick={toggleMuted}
        aria-label={muted ? "Unmute intro sound" : "Mute intro sound"}
        aria-pressed={muted}
        className="absolute bottom-6 right-6 inline-flex size-10 items-center justify-center rounded-full border border-white/15 bg-black/50 text-white/70 backdrop-blur-sm transition-colors hover:border-white/40 hover:text-white sm:bottom-10 sm:right-10"
      >
        {muted ? (
          <VolumeX className="size-4" aria-hidden="true" />
        ) : (
          <Volume2 className="size-4" aria-hidden="true" />
        )}
      </button>
    </div>
  );
}
