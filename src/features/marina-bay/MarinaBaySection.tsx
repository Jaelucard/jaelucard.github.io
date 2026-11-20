import { Component, lazy, Suspense, useState } from 'react';
import type { ReactNode } from 'react';
import { ROAD_HALF_WIDTH, TRACK, TRACK_VIEW, sampleTrack } from './track';
import './marina-bay.css';

const MarinaBayGame = lazy(() => import('./MarinaBayGame'));
const outline = TRACK.points.map((point) => `${point.x},${point.y}`).join(' ');
const start = sampleTrack(0);

function SingaporeFlag() {
  return (
    <svg className="mb-flag" viewBox="0 0 27 18" width="27" height="18" aria-hidden="true">
      <rect width="27" height="9" fill="#E8112D" />
      <rect y="9" width="27" height="9" fill="#F5F2EC" />
      <circle cx="7.4" cy="4.5" r="3.1" fill="#FFFFFF" />
      <circle cx="8.6" cy="4.5" r="2.75" fill="#E8112D" />
      <g fill="#FFFFFF">
        <circle cx="10.8" cy="2.6" r="0.6" />
        <circle cx="12.5" cy="3.8" r="0.6" />
        <circle cx="11.8" cy="5.8" r="0.6" />
        <circle cx="9.8" cy="5.8" r="0.6" />
        <circle cx="9.1" cy="3.8" r="0.6" />
      </g>
    </svg>
  );
}

class GameBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <div className="mb-load-error" role="alert">
      <h3>The circuit could not load.</h3>
      <p>Refresh the page to try again. The rest of the portfolio is still available.</p>
      <button className="mb-button mb-button-primary" onClick={() => window.location.reload()}>Reload page</button>
    </div>;
    return this.props.children;
  }
}

function CircuitPreview() {
  return <svg className="mb-preview" viewBox={`${TRACK_VIEW.x} ${TRACK_VIEW.y} ${TRACK_VIEW.width} ${TRACK_VIEW.height}`}
    role="img" aria-label="Complete 19-turn Marina Bay circuit, with the start on the main straight at the right">
    <defs>
      <pattern id="mb-grid" width="70" height="70" patternUnits="userSpaceOnUse"><path d="M 70 0 L 0 0 0 70" fill="none" stroke="#20302e" strokeWidth="1" /></pattern>
      <linearGradient id="mb-water" x1="0" y1="0" x2="1" y2="1"><stop stopColor="#122e32" /><stop offset="1" stopColor="#0e2027" /></linearGradient>
    </defs>
    <rect x={TRACK_VIEW.x} y={TRACK_VIEW.y} width={TRACK_VIEW.width} height={TRACK_VIEW.height} fill="#111d20" />
    <rect x={TRACK_VIEW.x} y={TRACK_VIEW.y} width={TRACK_VIEW.width} height={TRACK_VIEW.height} fill="url(#mb-grid)" />
    <path d="M410 485 Q590 620 1060 710 L1510 800 L1510 1080 L310 1080 Q375 880 420 720Z" fill="url(#mb-water)" />
    <text x="720" y="860" fill="#6c989f" fontSize="26" fontFamily="monospace" letterSpacing="9">MARINA BAY</text>
    <polyline points={outline} fill="none" stroke="#050d11" strokeWidth={ROAD_HALF_WIDTH * 2 + 15} strokeLinejoin="round" />
    <polyline points={outline} fill="none" stroke="#86918d" strokeWidth={ROAD_HALF_WIDTH * 2 + 4} strokeLinejoin="round" />
    <polyline points={outline} fill="none" stroke="#df3644" strokeWidth={ROAD_HALF_WIDTH * 2 + 4} strokeDasharray="13 13" strokeLinejoin="round" />
    <polyline points={outline} fill="none" stroke="#344045" strokeWidth={ROAD_HALF_WIDTH * 2} strokeLinejoin="round" />
    <polyline points={outline} fill="none" stroke="#839a9a" strokeWidth="1.4" strokeDasharray="9 17" strokeLinejoin="round" />
    <g transform={`translate(${start.x} ${start.y}) rotate(${start.angle * 180 / Math.PI})`}>
      <rect x="-18" y="-10" width="36" height="20" rx="4" fill="#ee2440" />
      <rect x="4" y="-7" width="8" height="14" rx="2" fill="#fff0df" />
    </g>
    <circle cx={start.x} cy={start.y} r="35" fill="none" stroke="#f0e8dc" strokeWidth="2" opacity=".6" />
    <text x="1312" y="344" textAnchor="middle" fill="#f0e8dc" fontSize="14" fontFamily="monospace" letterSpacing="2">START</text>
    <text x="1312" y="362" textAnchor="middle" fill="#b9cac5" fontSize="14" fontFamily="monospace" letterSpacing="2">FINISH</text>
    <g stroke="#6d9291" fill="none" opacity=".6"><circle cx="1267" cy="550" r="44" strokeWidth="3" /><circle cx="1267" cy="550" r="6" strokeWidth="3" /><path d="M1267 506V594M1223 550H1311M1236 519L1298 581M1298 519L1236 581M1267 550L1250 604M1267 550L1284 604" strokeWidth="2" /></g>
    <text x="0" y="-65" fill="#a7b5b2" fontSize="16" fontFamily="monospace" letterSpacing="3">01°17′ N / 103°51′ E</text>
    <text x="1430" y="1008" textAnchor="end" fill="#7b9395" fontSize="15" fontFamily="monospace" letterSpacing="3">SINGAPORE AFTER DARK</text>
  </svg>;
}

function Briefing({ loading, onStart }: { loading?: boolean; onStart?: () => void }) {
  return <div className="mb-board">
    <div className="mb-stage mb-stage-preview"><CircuitPreview /><div className="mb-map-caption"><span className="mb-live-dot" /> FULL CIRCUIT. YOUR RACING LINE.</div></div>
    <aside className="mb-pit-wall mb-briefing">
      <span className="mb-kicker">A little detour</span>
      <h3>Your city.<br />Your hot lap.</h3>
      <p>All 19 corners of Marina Bay. A tiny car, forgiving handling, and one more reason to stay a while.</p>
      <button type="button" className="mb-button mb-button-primary" onClick={onStart} disabled={loading}>
        {loading ? 'Opening the circuit…' : 'Start your lap'}<span aria-hidden="true">↗</span>
      </button>
      <div className="mb-control-summary mb-controls-keyboard">
        <span><kbd>W</kbd> Accelerate</span>
        <span><kbd>A</kbd><kbd>D</kbd> Steer</span>
        <span><kbd>S</kbd> Brake / reverse</span>
      </div>
      <div className="mb-control-summary mb-controls-touch">
        <span>Hold <strong>Accelerate</strong> + <strong>← / →</strong> together to steer through corners.</span>
      </div>
      <p className="mb-small mb-small-keyboard">Arrow keys work too. On-screen controls appear when you start.</p>
      <p className="mb-small mb-small-touch">Multi-touch pedals and steering appear as soon as the circuit opens.</p>
    </aside>
  </div>;
}

export function MarinaBaySection() {
  const [opened, setOpened] = useState(false);
  return <section id="marina-bay" className="section mb-section" aria-labelledby="mb-title">
    <div className="wrap">
      <div className="section-head"><p className="eyebrow">Off the clock</p><span className="mono section-index">Extra lap</span></div>
      <div className="mb-heading"><h2 id="mb-title" className="display section-title">One more <span>lap.</span></h2><p>A short break in Singapore.<br />A full lap of Marina Bay.</p></div>
      <div className="mb-shell">
        <div className="mb-topbar">
          <div className="mb-event">
            <SingaporeFlag />
            <strong>MARINA BAY</strong>
            <span className="mb-tag">ARCADE CLUB</span>
          </div>
          <span className="mb-circuit-info">4.927 KM <span aria-hidden="true">/</span> 19 TURNS</span>
        </div>
        {opened ? <GameBoundary><Suspense fallback={<Briefing loading />}><MarinaBayGame /></Suspense></GameBoundary> : <Briefing onStart={() => setOpened(true)} />}
        <div className="mb-bottom-bar"><span>Full circuit layout. Forgiving arcade handling.</span><a href="https://github.com/bacinger/f1-circuits" target="_blank" rel="noopener noreferrer">Circuit data: F1 Circuits <span aria-hidden="true">↗</span></a></div>
      </div>
    </div>
  </section>;
}
