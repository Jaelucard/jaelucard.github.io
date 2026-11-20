import { useEffect, useRef, useState } from 'react';
import type { Playback } from './playback';
import { fetchPlayback, formatTime, isStale } from './playback';
import { startPlaybackPolling } from './polling';
import spotifyLogo from './spotify-logo-white.svg';
import './spotify.css';

const unavailable: Playback = { status: 'unavailable' };
const staleMs = 90_000;

function usePlayback() {
  const [playback, setPlayback] = useState<Playback>(unavailable);
  const [now, setNow] = useState(0);

  useEffect(() => {
    const endpoint = process.env.NEXT_PUBLIC_SPOTIFY_STATUS_URL;
    const fallback = process.env.NEXT_PUBLIC_SPOTIFY_FALLBACK_URL;
    if (!endpoint) return;
    return startPlaybackPolling(
      (signal) => fetchPlayback(endpoint, fallback, signal),
      (parsed) => {
        setPlayback(parsed ?? unavailable);
        setNow(Date.now());
      },
    );
  }, []);

  const isPlaying = playback.status === 'playing';
  useEffect(() => {
    if (!isPlaying) return;
    const ticker = setInterval(() => {
      if (document.visibilityState !== 'hidden') setNow(Date.now());
    }, 1000);
    return () => clearInterval(ticker);
  }, [isPlaying]);

  if (isStale(playback, now, staleMs)) return { playback: unavailable, now };
  return { playback, now };
}

export function SpotifySection() {
  const { playback, now } = usePlayback();
  const { status, track } = playback;
  const [entered, setEntered] = useState(false);
  const sectionRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const section = sectionRef.current;
    if (!section) return;
    if (!('IntersectionObserver' in window)) {
      setEntered(true);
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        setEntered(true);
        observer.disconnect();
      }
    }, { threshold: 0.05 });
    observer.observe(section);
    return () => observer.disconnect();
  }, []);

  const active = status === 'playing';
  const observed = playback.fetchedAt ? Date.parse(playback.fetchedAt) : now;
  const duration = track?.durationMs;
  const progress = track?.progressMs === undefined ? undefined : Math.min(
    track.progressMs + (active && observed ? Math.max(0, now - observed) : 0),
    duration ?? Infinity,
  );
  const hasTiming = progress !== undefined && duration !== undefined && duration > 0;
  const label = status === 'playing'
    ? 'Now listening'
    : status === 'paused'
      ? 'Playback paused'
      : status === 'offline'
        ? 'Not listening'
        : 'Playback unavailable';

  return (
    <section ref={sectionRef} id="radio" className="spotify-section" aria-labelledby="spotify-heading">
      <div className="wrap">
        <div className="section-head">
          <h2 id="spotify-heading" className="eyebrow">Radio Check</h2>
          <p className="mono section-index">Pit Wall</p>
        </div>

        {!track ? (
          <div
            className={`spotify-broadcast spotify-standby${entered ? ' spotify-entered' : ''}`}
            data-state={status}
          >
            <div className="spotify-standby-lead" aria-live="polite">
              <i className="spotify-standby-dot" aria-hidden="true" />
              <span className="spotify-standby-kicker mono">{label}</span>
              <span className="spotify-standby-sep" aria-hidden="true">/</span>
              <strong className="spotify-standby-title">
                {status === 'offline' ? 'Off air' : 'Radio quiet'}
              </strong>
            </div>
            <div className="spotify-standby-meta">
              <div className="spotify-mini-bars" aria-hidden="true">
                <i /><i /><i /><i /><i />
              </div>
              <span className="spotify-standby-session mono">
                {status === 'offline' ? 'Standby' : 'Unavailable'}
              </span>
              <img className="spotify-standby-logo" src={spotifyLogo.src} alt="Spotify" />
            </div>
          </div>
        ) : (
          <div
            className={`spotify-broadcast${entered ? ' spotify-entered' : ''}`}
            data-state={status}
          >
            <div className="spotify-top">
              <div className="spotify-status" aria-live="polite">
                <i aria-hidden="true" />
                <span>{label}</span>
              </div>
              <div className="spotify-frequency">
                Pit wall <span aria-hidden="true">/</span> Radio check
              </div>
              <div className="spotify-sign-cluster">
                <div className="spotify-flags" aria-hidden="true">
                  <i /><i /><i /><i /><i /><i />
                </div>
                <div className="spotify-sign">
                  JL <span aria-hidden="true">▰</span> 01
                </div>
              </div>
            </div>
            <div className="spotify-main">
              <div className="spotify-rail" aria-hidden="true">
                <span>Driver&apos;s<br />radio</span>
                <div className="spotify-synth">
                  <div className="spotify-bars"><i /><i /><i /><i /><i /><i /><i /></div>
                  <small>Synth</small>
                </div>
                <span>Music<br />feed</span>
              </div>
              <div className={`spotify-track${track.artworkUrl ? '' : ' no-art'}`}>
                {track.artworkUrl && (
                  <a
                    className="spotify-art"
                    href={track.spotifyUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={`Open ${track.title} on Spotify`}
                  >
                    <img src={track.artworkUrl} alt="" />
                  </a>
                )}
                <div className="spotify-info" key={track.spotifyUrl}>
                  <p className="spotify-kicker">{label}</p>
                  <a
                    className="spotify-track-link"
                    href={track.spotifyUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <span className="spotify-name">{track.title}</span>
                    <span className="spotify-artist">{track.artist}</span>
                  </a>
                  {hasTiming && (
                    <>
                      <div
                        className="spotify-progress"
                        role="progressbar"
                        aria-label="Playback progress"
                        aria-valuemin={0}
                        aria-valuemax={Math.floor(duration / 1000)}
                        aria-valuenow={Math.floor(progress / 1000)}
                      >
                        <span style={{ width: `${Math.min(100, (progress / duration) * 100)}%` }} />
                      </div>
                      <div className="spotify-clock">
                        <span>{formatTime(progress)}</span>
                        <span>{formatTime(duration)}</span>
                      </div>
                    </>
                  )}
                </div>
              </div>
            </div>
            <div className="spotify-bottom">
              <div>
                <span>Session</span>
                <strong>{status === 'playing' ? 'Listening' : 'Paused'}</strong>
              </div>
              <div className="spotify-source">
                <span>Source</span>
            <img src={spotifyLogo.src} alt="Spotify" />
              </div>
              <a
                className="spotify-open"
                href={track.spotifyUrl}
                target="_blank"
                rel="noopener noreferrer"
              >
                Open Spotify <b aria-hidden="true">↗</b>
              </a>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
