import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { INTRO_CONFIG, type IntroMedia } from '../../config/intro';

type Variant = keyof typeof INTRO_CONFIG.media;
type Phase = 'loading' | 'playing' | 'handoff' | 'settle';
type Run = { variant: Variant; mode: 'video' | 'placeholder'; phase: Phase; skipped: boolean };

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
    const mode = media[variant] ? 'video' : 'placeholder';
    setRun({ variant, mode, phase: mode === 'video' ? 'loading' : 'playing', skipped: false });
  }, [media]);

  useLayoutEffect(() => {
    const root = document.documentElement;
    setCapture(root.dataset.capture === 'hero');
    if (root.dataset.intro === 'pending') start();
  }, [start]);

  const phase = run?.phase;
  const mode = run?.mode;
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
    setRun((current) => current && (current.phase === 'loading' || current.phase === 'playing')
      ? { ...current, phase: 'handoff', skipped: skip }
      : current);
  }, []);

  const skip = useCallback(() => handoff(true), [handoff]);

  const abort = useCallback(() => {
    focusMain.current = overlayRef.current?.contains(document.activeElement) ?? false;
    setRun(null);
  }, []);

  const onVideoError = useCallback(() => {
    if (process.env.NODE_ENV === 'development') {
      setRun((current) => current && (current.phase === 'loading' || current.phase === 'playing')
        ? { ...current, mode: 'placeholder', phase: 'playing' }
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
    const timer = mode === 'placeholder'
      ? window.setTimeout(handoff, INTRO_CONFIG.handoffTimeSec * 1000)
      : window.setTimeout(abort, INTRO_CONFIG.durationSec * 1000 + INTRO_CONFIG.loadTimeoutMs);
    return () => window.clearTimeout(timer);
  }, [abort, handoff, mode, phase]);

  useEffect(() => {
    const video = videoRef.current;
    if (mode !== 'video' || !video) return;

    let active = true;
    let frame = 0;
    const onFrame: VideoFrameRequestCallback = (_now, { mediaTime }) => {
      if (mediaTime >= INTRO_CONFIG.handoffTimeSec) handoff();
      else if (active) frame = video.requestVideoFrameCallback(onFrame);
    };
    if ('requestVideoFrameCallback' in video) frame = video.requestVideoFrameCallback(onFrame);

    video.play().catch((error: DOMException) => {
      if (!active) return;
      if (error.name === 'NotSupportedError') onVideoError();
      else abort();
    });
    return () => {
      active = false;
      if (frame) video.cancelVideoFrameCallback(frame);
    };
  }, [abort, handoff, mode, onVideoError]);

  useEffect(() => {
    if (phase !== 'handoff') return;
    focusMain.current = skipped || Boolean(overlayRef.current?.contains(document.activeElement));
    try { localStorage.setItem(INTRO_CONFIG.storageKey, 'true'); } catch { /* Storage is optional. */ }
    const timer = window.setTimeout(() => {
      setRun((current) => current && !skipped ? { ...current, phase: 'settle' } : null);
    }, skipped ? INTRO_CONFIG.skipFadeMs : INTRO_CONFIG.handoffFadeMs);
    return () => window.clearTimeout(timer);
  }, [phase, skipped]);

  useEffect(() => {
    if (phase !== 'settle') return;
    const timer = window.setTimeout(() => setRun(null), INTRO_CONFIG.heroSettleMs - INTRO_CONFIG.handoffFadeMs);
    return () => window.clearTimeout(timer);
  }, [phase]);

  useEffect(() => {
    if (!blocked) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault();
        skip();
      } else if (event.key === 'Tab') {
        event.preventDefault();
        overlayRef.current?.querySelector('button')?.focus();
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

  return { run, capture, blocked, videoRef, overlayRef, mainRef, onPlaying, onVideoError, handoff, skip, replay };
}
