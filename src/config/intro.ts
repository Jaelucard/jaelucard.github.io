export const INTRO_VIDEOS = {
  singaporeWheel: {
    fps: 24,
    durationSec: 5.5,
    handoffTimeSec: null,
    handoffFadeMs: 0,
    sound: true,
    media: {
      desktop: {
        webm: '/media/singapore-wheel-720p-intro-desktop.webm',
        mp4: '/media/singapore-wheel-720p-intro-desktop.mp4',
        poster: '/media/singapore-wheel-720p-intro-poster-desktop.webp',
      },
      mobile: {
        webm: '/media/singapore-wheel-720p-intro-mobile.webm',
        mp4: '/media/singapore-wheel-720p-intro-mobile.mp4',
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

export type IntroPoint = readonly [x: number, y: number];
export type IntroQuad = readonly [topLeft: IntroPoint, topRight: IntroPoint, bottomRight: IntroPoint, bottomLeft: IntroPoint];
export type WheelScreenTrack = Readonly<{
  width: number;
  height: number;
  corners: IntroQuad;
}>;

export const WHEEL_SCREEN = {
  appearSec: 3.75,
  zoomSec: 4.35,
  fullSec: 5.42,
  desktop: {
    width: 1280,
    height: 720,
    corners: [[548, 418], [724, 418], [725, 485], [548, 485]],
  },
  mobile: {
    width: 720,
    height: 1280,
    corners: [[268, 713], [455, 713], [455, 789], [268, 789]],
  },
} as const satisfies Record<IntroVariant, WheelScreenTrack> & { appearSec: number; zoomSec: number; fullSec: number };

export const INTRO_CONFIG = {
  storageKey: 'jarrod_f1_intro_seen_v1',
  heroSettleMs: 380,
  skipFadeMs: 220,
  skipRevealDelayMs: 400,
  loadTimeoutMs: 2500,
  mobileBreakpointPx: 768,
  captureQuoteIndex: 0,
} as const;

export type IntroVideo = keyof typeof INTRO_VIDEOS;
export type IntroVariant = keyof typeof INTRO_VIDEOS.singaporeWheel.media;
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
    if (navigator.connection?.saveData || location.hash) return;
    try { if (localStorage.getItem(${JSON.stringify(INTRO_CONFIG.storageKey)})) return; } catch {}
  }
  root.dataset.intro = 'pending';
  setTimeout(() => {
    if (root.dataset.intro === 'pending') delete root.dataset.intro;
  }, ${INTRO_CONFIG.loadTimeoutMs});
})();`;
