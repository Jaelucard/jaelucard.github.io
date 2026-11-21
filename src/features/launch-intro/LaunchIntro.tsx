import { useState, type CSSProperties } from 'react';
import { Hero } from '../../components/Hero';
import { INTRO_CONFIG, INTRO_VIDEOS } from '../../config/intro';
import { IntroPlaceholder } from './IntroPlaceholder';
import type { useIntroController } from './useIntroController';
import './launch-intro.css';

export function LaunchIntro({ intro }: { intro: ReturnType<typeof useIntroController> }) {
  const [soundOn, setSoundOn] = useState(false);
  const run = intro.run;
  if (!run) return null;

  const videoConfig = run.video ? INTRO_VIDEOS[run.video] : null;
  const media = videoConfig?.media[run.variant];
  const handoffTimeSec = videoConfig?.handoffTimeSec;
  const style = {
    '--intro-skip-delay': `${INTRO_CONFIG.skipRevealDelayMs}ms`,
    '--intro-fade-duration': `${run.skipped ? INTRO_CONFIG.skipFadeMs : intro.handoffFadeMs}ms`,
  } as CSSProperties;

  function toggleSound() {
    const video = intro.videoRef.current;
    if (!video) return;
    video.muted = !video.muted;
    setSoundOn(!video.muted);
  }

  return (
    <section
      ref={intro.overlayRef}
      role="region"
      aria-label="F1 cockpit launch animation"
      className="launch-intro"
      data-phase={run.phase}
      data-transition={run.video === 'singaporeNeutral' && !run.skipped ? 'neutral' : undefined}
      tabIndex={-1}
      style={style}
    >
      {media ? (
        <video
          ref={intro.videoRef}
          className="launch-intro-video"
          aria-hidden="true"
          autoPlay
          muted={!soundOn}
          playsInline
          preload="auto"
          poster={media.poster}
          onPlaying={intro.onPlaying}
          onEnded={() => intro.handoff()}
          onVolumeChange={({ currentTarget: video }) => setSoundOn(!video.muted)}
          onError={(event) => {
            if (run.phase !== 'handoff' && event.target === event.currentTarget) intro.onVideoError();
          }}
          onTimeUpdate={({ currentTarget: video }) => {
            if (handoffTimeSec != null && !video.requestVideoFrameCallback && video.currentTime >= handoffTimeSec) {
              intro.handoff();
            }
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
      <div className="launch-intro-controls">
        <button className="launch-intro-control mono" type="button" onClick={intro.skip} disabled={run.phase === 'handoff'}>
          Skip intro <span aria-hidden="true">→</span>
        </button>
        {videoConfig?.sound && (
          <button className="launch-intro-control mono" type="button" onClick={toggleSound} disabled={run.phase === 'handoff'}>
            {soundOn ? 'Sound off' : 'Sound on'}
          </button>
        )}
      </div>
    </section>
  );
}
