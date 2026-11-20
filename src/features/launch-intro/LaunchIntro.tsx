import type { CSSProperties } from 'react';
import { Hero } from '../../components/Hero';
import { INTRO_CONFIG } from '../../config/intro';
import { IntroPlaceholder } from './IntroPlaceholder';
import type { useIntroController } from './useIntroController';
import './launch-intro.css';

export function LaunchIntro({ intro }: { intro: ReturnType<typeof useIntroController> }) {
  const run = intro.run;
  if (!run) return null;

  const media = INTRO_CONFIG.media[run.variant];
  const style = {
    '--intro-skip-delay': `${INTRO_CONFIG.skipRevealDelayMs}ms`,
    '--intro-fade-duration': `${run.skipped ? INTRO_CONFIG.skipFadeMs : INTRO_CONFIG.handoffFadeMs}ms`,
  } as CSSProperties;

  return (
    <section
      ref={intro.overlayRef}
      role="region"
      aria-label="F1 cockpit launch animation"
      className="launch-intro"
      data-phase={run.phase}
      tabIndex={-1}
      style={style}
    >
      {run.mode === 'video' ? (
        <video
          ref={intro.videoRef}
          className="launch-intro-video"
          aria-hidden="true"
          autoPlay
          muted
          playsInline
          preload="auto"
          poster={media.poster}
          onPlaying={intro.onPlaying}
          onEnded={() => intro.handoff()}
          onError={(event) => {
            if (run.phase !== 'handoff' && event.target === event.currentTarget) intro.onVideoError();
          }}
          onTimeUpdate={({ currentTarget: video }) => {
            if (!video.requestVideoFrameCallback && video.currentTime >= INTRO_CONFIG.handoffTimeSec) intro.handoff();
          }}
        >
          <source src={media.webm} type="video/webm" />
          <source src={media.mp4} type="video/mp4" onError={run.phase === 'handoff' ? undefined : intro.onVideoError} />
        </video>
      ) : (
        <IntroPlaceholder>
          <div className="launch-intro-hero-preview">
            <Hero preview />
          </div>
        </IntroPlaceholder>
      )}
      <button className="launch-intro-skip mono" type="button" onClick={intro.skip}>
        Skip intro <span aria-hidden="true">→</span>
      </button>
    </section>
  );
}
