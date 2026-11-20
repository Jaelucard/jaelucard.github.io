import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { INTRO_CONFIG, INTRO_VIDEOS, type IntroMedia, type IntroVariant, type IntroVideo } from '../../config/intro';

type Phase = 'loading' | 'playing' | 'handoff' | 'settle';
type Run = { variant: IntroVariant; video: IntroVideo | null; phase: Phase; skipped: boolean };

const reducedMotion = '(prefers-reduced-motion: reduce)';

export function useIntroController(media: IntroMedia) {
  const [run, setRun] = useState<Run | null>(null);
  const [capture, setCapture] = useState(false);
  const [replayPending, setReplayPending] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const overlayRef = useRef<HTMLElement>(null);
  const mainRef = useRef<HTMLElement>(null);
  const focusMain = useRef(false);

  const start = useCallback(() => {
    const variant = matchMedia(`(max-width: ${INTRO_CONFIG.mobileBreakpointPx}px)`).matches ? 'mobile' : 'desktop';
    const video = media[variant];
    setRun({ variant, video, phase: video ? 'loading' : 'playing', skipped: false });
  }, [media]);

  useLayoutEffect(() => {
    const root = document.documentElement;
    setCapture(root.dataset.capture === 'hero');
    if (root.dataset.intro === 'pending') start();
  }, [start]);

  const phase = run?.phase;
  const videoConfig = run?.video ? INTRO_VIDEOS[run.video] : null;
  const handoffFadeMs = (videoConfig ?? INTRO_VIDEOS.legacy).handoffFadeMs;
  const skipped = run?.skipped ?? false;
  const blocked = Boolean(phase && phase !== 'settle');

  useLayoutEffect(() => {
    const root = document.documentElement;
    if (blocked) {
      root.dataset.intro = 'active';
      overlayRef.current?.focus({ preventScroll: true });
      return;
    }
    if (root.dataset.intro === 'active') delete root.dataset.intro;
    if (focusMain.current) {
      focusMain.current = false;
      mainRef.current?.focus({ preventScroll: true });
    }
  }, [blocked]);

  const handoff = useCallback((skip = false) => {
    if (skip || overlayRef.current?.contains(document.activeElement)) focusMain.current = true;
    setRun((current) => current && (current.phase === 'loading' || current.phase === 'playing')
      ? { ...current, phase: 'handoff', skipped: skip }
      : current);
  }, []);

  const skip = useCallback(() => handoff(true), [handoff]);

  const abort = useCallback(() => {
    if (overlayRef.current?.contains(document.activeElement)) focusMain.current = true;
    setRun(null);
  }, []);

  const onVideoError = useCallback(() => {
    if (process.env.NODE_ENV === 'development') {
      setRun((current) => current && (current.phase === 'loading' || current.phase === 'playing')
        ? { ...current, video: null, phase: 'playing' }
        : current);
      return;
    }
    abort();
  }, [abort]);

  const onPlaying = useCallback(() => {
    setRun((current) => current?.phase === 'loading' ? { ...current, phase: 'playing' } : current);
  }, []);

  useEffect(() => {
    if (phase !== 'loading') return;
    const timer = window.setTimeout(abort, INTRO_CONFIG.loadTimeoutMs);
    return () => window.clearTimeout(timer);
  }, [abort, phase]);

  useEffect(() => {
    if (phase !== 'playing') return;
    const timer = videoConfig
      ? window.setTimeout(abort, videoConfig.durationSec * 1000 + INTRO_CONFIG.loadTimeoutMs)
      : window.setTimeout(handoff, INTRO_VIDEOS.legacy.handoffTimeSec * 1000);
    return () => window.clearTimeout(timer);
  }, [abort, handoff, phase, videoConfig]);

  useEffect(() => {
    const video = videoRef.current;
    if (!videoConfig || !video) return;

    let active = true;
    let frame = 0;
    const handoffTimeSec = videoConfig.handoffTimeSec;
    const onFrame: VideoFrameRequestCallback = (_now, { mediaTime }) => {
      if (handoffTimeSec !== null && mediaTime >= handoffTimeSec) handoff();
      else if (active) frame = video.requestVideoFrameCallback(onFrame);
    };
    if (handoffTimeSec !== null && 'requestVideoFrameCallback' in video) {
      frame = video.requestVideoFrameCallback(onFrame);
    }

    video.play().catch((error: DOMException) => {
      if (!active) return;
      if (error.name === 'NotSupportedError') onVideoError();
      else abort();
    });
    return () => {
      active = false;
      if (frame) video.cancelVideoFrameCallback(frame);
    };
  }, [abort, handoff, onVideoError, videoConfig]);

  useEffect(() => {
    if (phase !== 'handoff') return;
    try { localStorage.setItem(INTRO_CONFIG.storageKey, 'true'); } catch { /* Storage is optional. */ }
    const timer = window.setTimeout(() => {
      setRun((current) => current && !skipped ? { ...current, phase: 'settle' } : null);
    }, skipped ? INTRO_CONFIG.skipFadeMs : handoffFadeMs);
    return () => window.clearTimeout(timer);
  }, [handoffFadeMs, phase, skipped]);

  useEffect(() => {
    if (phase !== 'settle') return;
    const timer = window.setTimeout(() => setRun(null), INTRO_CONFIG.heroSettleMs - handoffFadeMs);
    return () => window.clearTimeout(timer);
  }, [handoffFadeMs, phase]);

  useEffect(() => {
    if (!blocked) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault();
        skip();
      } else if (event.key === 'Tab') {
        event.preventDefault();
        const buttons = Array.from(overlayRef.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? []);
        const index = buttons.findIndex((button) => button === document.activeElement);
        const next = index < 0
          ? (event.shiftKey ? buttons.length - 1 : 0)
          : (index + (event.shiftKey ? -1 : 1) + buttons.length) % buttons.length;
        buttons[next]?.focus();
      }
    }
    const preference = matchMedia(reducedMotion);
    const onMotionChange = (event: MediaQueryListEvent) => { if (event.matches) abort(); };
    window.addEventListener('keydown', onKeyDown);
    preference.addEventListener('change', onMotionChange);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      preference.removeEventListener('change', onMotionChange);
    };
  }, [abort, blocked, skip]);

  useEffect(() => {
    if (!replayPending) return;
    function playFromTop() {
      window.scrollTo({ top: 0, behavior: 'instant' });
      setReplayPending(false);
      if (!matchMedia(reducedMotion).matches) start();
    }
    if (window.scrollY === 0) {
      playFromTop();
      return;
    }
    window.addEventListener('scrollend', playFromTop, { once: true });
    window.scrollTo({ top: 0, behavior: 'smooth' });
    const timer = window.setTimeout(playFromTop, 900);
    return () => {
      window.removeEventListener('scrollend', playFromTop);
      window.clearTimeout(timer);
    };
  }, [replayPending, start]);

  function replay() {
    if (capture || matchMedia(reducedMotion).matches) return;
    setReplayPending(true);
  }

  return { run, capture, blocked, handoffFadeMs, videoRef, overlayRef, mainRef, onPlaying, onVideoError, handoff, skip, replay };
}
