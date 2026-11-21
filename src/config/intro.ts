export const INTRO_VIDEOS = {
  singaporeNeutral: {
    fps: 24,
    durationSec: 5.5,
    handoffTimeSec: null,
    handoffFadeMs: 1400,
    sound: true,
    media: {
      desktop: {
        webm: '/media/singapore-neutral-720p-intro-desktop.webm',
        mp4: '/media/singapore-neutral-720p-intro-desktop.mp4',
        poster: '/media/singapore-wheel-720p-intro-poster-desktop.webp',
      },
      mobile: {
        webm: '/media/singapore-neutral-720p-intro-mobile.webm',
        mp4: '/media/singapore-neutral-720p-intro-mobile.mp4',
        poster: '/media/singapore-wheel-720p-intro-poster-mobile.webp',
      },
    },
  },
  legacy: {
    fps: 30,
    durationSec: 5.2,
    handoffTimeSec: 4.85,
    handoffFadeMs: 260,
    sound: false,
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
  },
} as const;

export const INTRO_CONFIG = {
  heroSettleMs: 380,
  skipFadeMs: 220,
  skipRevealDelayMs: 400,
  loadTimeoutMs: 2500,
  mobileBreakpointPx: 768,
  captureQuoteIndex: 0,
} as const;

export type IntroVideo = keyof typeof INTRO_VIDEOS;
export type IntroVariant = keyof typeof INTRO_VIDEOS.singaporeNeutral.media;
export type IntroMedia = Readonly<Record<IntroVariant, IntroVideo | null>>;

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
    const navigation = performance.getEntriesByType('navigation')[0];
    if (navigator.connection?.saveData || location.hash || navigation?.type === 'back_forward') return;
  }
  root.dataset.intro = 'pending';
  setTimeout(() => {
    if (root.dataset.intro === 'pending') delete root.dataset.intro;
  }, ${INTRO_CONFIG.loadTimeoutMs});
})();`;
