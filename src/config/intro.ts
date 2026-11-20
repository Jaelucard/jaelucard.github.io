export const INTRO_CONFIG = {
  storageKey: 'jarrod_f1_intro_seen_v1',
  fps: 30,
  durationSec: 5.2,
  handoffTimeSec: 4.85,
  handoffFadeMs: 260,
  heroSettleMs: 380,
  skipFadeMs: 220,
  skipRevealDelayMs: 400,
  loadTimeoutMs: 2500,
  mobileBreakpointPx: 768,
  // Keep the live Hero on the same quote as the rendered tablet during the fade.
  captureQuoteIndex: 0,
  media: {
    desktop: {
      webm: '/media/intro-desktop.webm',
      mp4: '/media/intro-desktop.mp4',
      poster: '/media/intro-poster-desktop.webp',
    },
    mobile: {
      webm: '/media/intro-mobile.webm',
      mp4: '/media/intro-mobile.mp4',
      poster: '/media/intro-poster-mobile.webp',
    },
  },
} as const;

export type IntroMedia = Readonly<Record<keyof typeof INTRO_CONFIG.media, boolean>>;

// Runs before hydration so the first paint is either the curtain or the portfolio.
export const INTRO_BOOT_SCRIPT = `(() => {
  const root = document.documentElement;
  const query = new URLSearchParams(location.search);
  if (query.get('capture') === 'hero') {
    root.dataset.capture = 'hero';
    return;
  }
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  if (query.get('intro') !== '1') {
    if (navigator.connection?.saveData || location.hash) return;
    try { if (localStorage.getItem(${JSON.stringify(INTRO_CONFIG.storageKey)})) return; } catch {}
  }
  root.dataset.intro = 'pending';
  setTimeout(() => {
    if (root.dataset.intro === 'pending') delete root.dataset.intro;
  }, ${INTRO_CONFIG.loadTimeoutMs});
})();`;
