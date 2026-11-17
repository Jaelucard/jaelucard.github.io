import { useEffect, useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';
import { createRenderer } from './renderer';
import { CHECKPOINT_COUNT, INPUT_IDLE, SIMULATION_STEP, createGame, formatLapTime, resetGame, updateGame } from './simulation';
import type { GameState, InputState } from './simulation';
import { readBestLap, saveBestLap } from './storage';

type Action = keyof InputState;
type Controller = {
  pause(reason?: string): void;
  resume(reason?: string): void;
  restart(): void;
  press(action: Action, pointer: number, down: boolean): void;
};
type DebugController = {
  snapshot(): GameState & { paused: boolean };
  /** Advance seconds with a fixed timestep while normal animation is paused. */
  advance(seconds: number): void;
  setInput(input: Partial<InputState>): void;
};
declare global { interface Window { __MARINA_BAY_GAME__?: DebugController } }
const KEY_ACTION: Record<string, Action> = {
  KeyW: 'throttle', ArrowUp: 'throttle', KeyS: 'brake', ArrowDown: 'brake',
  KeyA: 'left', ArrowLeft: 'left', KeyD: 'right', ArrowRight: 'right',
};
const ACTIONS: Action[] = ['throttle', 'brake', 'left', 'right'];

export default function MarinaBayGame() {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const gameRef = useRef<GameState | null>(null);
  const controlsRef = useRef<Controller | null>(null);
  const [hud, setHud] = useState(createGame);
  const [paused, setPaused] = useState(false);
  const [held, setHeld] = useState<InputState>({ ...INPUT_IDLE });
  const [announcement, setAnnouncement] = useState('Circuit ready. Hold W to accelerate.');
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    const host = hostRef.current;
    if (!canvas || !host) return;
    const game = gameRef.current ??= createGame(readBestLap());
    let renderer: ReturnType<typeof createRenderer>;
    try { renderer = createRenderer(canvas); }
    catch { setUnavailable(true); return; }
    const input: InputState = { ...INPUT_IDLE };
    const keys = new Set<string>();
    const pointers = new Map<number, Action>();
    let running = true;
    let disposed = false;
    let frameId = 0;
    let previousTime = 0;
    let accumulator = 0;
    let lastHudTime = 0;
    let lastResult = game.lastResultId;
    let savedBest = game.bestLap;

    function syncInput() {
      for (const action of ACTIONS) input[action] = [...keys].some((key) => KEY_ACTION[key] === action)
        || [...pointers.values()].includes(action);
      setHeld({ ...input });
    }
    function clearInput() { keys.clear(); pointers.clear(); syncInput(); }
    function publish(force = false, now = performance.now()) {
      if (game.lastResultId !== lastResult) {
        lastResult = game.lastResultId;
        let message = game.lastLapValid ? `Lap complete: ${formatLapTime(game.lastLap)}.`
          : 'Lap not recorded. Pass every checkpoint in order before the finish.';
        if (game.bestLap !== null && (savedBest === null || game.bestLap < savedBest)) {
          const candidate = game.bestLap;
          const saved = saveBestLap(candidate);
          const stored = readBestLap();
          if (stored !== null && stored < candidate) game.bestLap = stored;
          savedBest = game.bestLap;
          message = game.bestLap < candidate
            ? `Lap complete: ${formatLapTime(game.lastLap)}. Browser best: ${formatLapTime(game.bestLap)}.`
            : `New best: ${formatLapTime(game.bestLap)}.${saved ? ' Saved on this browser.' : ' Storage is unavailable; kept for this session.'}`;
        }
        setAnnouncement(message);
        force = true;
      }
      if (force || now - lastHudTime >= 100) { setHud({ ...game }); lastHudTime = now; }
    }
    function frame(now: number) {
      if (disposed || !running) return;
      if (!previousTime) previousTime = now;
      accumulator += Math.min((now - previousTime) / 1000, 0.1);
      previousTime = now;
      while (accumulator >= SIMULATION_STEP) {
        updateGame(game, input, SIMULATION_STEP);
        accumulator -= SIMULATION_STEP;
      }
      renderer.draw(game);
      publish(false, now);
      frameId = requestAnimationFrame(frame);
    }
    function pause(reason = 'Paused. Resume when you are ready.') {
      clearInput();
      if (!running) return;
      running = false;
      cancelAnimationFrame(frameId);
      accumulator = 0;
      previousTime = 0;
      setPaused(true);
      setAnnouncement(reason);
      renderer.draw(game);
      publish(true);
    }
    function resume(reason = 'Back on track. Hold W to accelerate.') {
      if (disposed || document.hidden) return;
      clearInput();
      canvas?.focus({ preventScroll: true });
      if (!running) {
        running = true;
        previousTime = 0;
        accumulator = 0;
        frameId = requestAnimationFrame(frame);
      }
      setPaused(false);
      setAnnouncement(reason);
    }
    const controller: Controller = {
      pause, resume,
      restart() {
        resetGame(game);
        accumulator = 0;
        previousTime = 0;
        renderer.draw(game);
        publish(true);
        resume('Lap restarted. Your saved best is kept.');
      },
      press(action, pointer, down) {
        if (down && running) pointers.set(pointer, action);
        else pointers.delete(pointer);
        syncInput();
      },
    };
    controlsRef.current = controller;

    function keyDown(event: KeyboardEvent) {
      if (document.activeElement !== canvas || event.altKey || event.ctrlKey || event.metaKey) return;
      const action = KEY_ACTION[event.code];
      if (action) {
        event.preventDefault();
        if (running && !keys.has(event.code)) { keys.add(event.code); syncInput(); }
      } else if (!event.repeat && (event.code === 'KeyP' || event.code === 'Escape')) {
        event.preventDefault();
        if (running) pause(); else if (event.code === 'KeyP') resume();
      } else if (!event.repeat && event.code === 'KeyR') {
        event.preventDefault(); controller.restart();
      }
    }
    function keyUp(event: KeyboardEvent) { if (keys.delete(event.code)) syncInput(); }
    const blur = () => pause('Paused while you were away. Resume to continue.');
    const visibility = () => { if (document.hidden) blur(); };
    const resize = () => { renderer.resize(); renderer.draw(game); };
    const resizeObserver = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(resize);
    resizeObserver?.observe(canvas.parentElement ?? canvas);
    const intersection = typeof IntersectionObserver === 'undefined' ? null : new IntersectionObserver((entries) => {
      if (!entries[0]?.isIntersecting) pause('Paused while the game is off screen.');
    });
    intersection?.observe(canvas);
    window.addEventListener('keydown', keyDown);
    window.addEventListener('keyup', keyUp);
    window.addEventListener('blur', blur);
    window.addEventListener('resize', resize);
    document.addEventListener('visibilitychange', visibility);
    resize();
    publish(true);
    canvas.focus({ preventScroll: true });
    frameId = requestAnimationFrame(frame);

    let debug: DebugController | undefined;
    if (import.meta.env.DEV) {
      let debugInput: InputState = { ...INPUT_IDLE };
      debug = {
        snapshot: () => ({ ...game, paused: !running }),
        setInput(value) { debugInput = { ...INPUT_IDLE, ...value }; },
        advance(seconds) {
          if (!Number.isFinite(seconds) || seconds < 0) return;
          pause('Paused for development stepping.');
          let remaining = Math.min(seconds, 600);
          while (remaining > 1e-9) {
            const dt = Math.min(remaining, SIMULATION_STEP);
            updateGame(game, debugInput, dt); remaining -= dt;
          }
          renderer.draw(game); publish(true);
        },
      };
      window.__MARINA_BAY_GAME__ = debug;
    }
    return () => {
      disposed = true;
      running = false;
      cancelAnimationFrame(frameId);
      resizeObserver?.disconnect(); intersection?.disconnect();
      window.removeEventListener('keydown', keyDown);
      window.removeEventListener('keyup', keyUp);
      window.removeEventListener('blur', blur);
      window.removeEventListener('resize', resize);
      document.removeEventListener('visibilitychange', visibility);
      renderer.destroy();
      if (controlsRef.current === controller) controlsRef.current = null;
      if (debug && window.__MARINA_BAY_GAME__ === debug) delete window.__MARINA_BAY_GAME__;
    };
  }, []);

  function pointerDown(event: ReactPointerEvent<HTMLButtonElement>, action: Action) {
    event.preventDefault();
    if (paused) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    canvasRef.current?.focus({ preventScroll: true });
    controlsRef.current?.press(action, event.pointerId, true);
  }
  function touchButton(action: Action, label: string, description: string) {
    const keyboardId = -ACTIONS.indexOf(action) - 1;
    return <button type="button" className="mb-touch-button" data-action={action} data-held={held[action]}
      aria-label={description} aria-pressed={held[action]} disabled={paused}
      onPointerDown={(event) => pointerDown(event, action)}
      onPointerUp={(event) => controlsRef.current?.press(action, event.pointerId, false)}
      onPointerCancel={(event) => controlsRef.current?.press(action, event.pointerId, false)}
      onLostPointerCapture={(event) => controlsRef.current?.press(action, event.pointerId, false)}
      onContextMenu={(event) => event.preventDefault()}
      onKeyDown={(event) => {
        if (event.code === 'Space' || event.code === 'Enter') {
          event.preventDefault(); controlsRef.current?.press(action, keyboardId, true);
        }
      }}
      onKeyUp={(event) => {
        if (event.code === 'Space' || event.code === 'Enter') {
          event.preventDefault(); controlsRef.current?.press(action, keyboardId, false);
        }
      }} onBlur={() => controlsRef.current?.press(action, keyboardId, false)}>{label}</button>;
  }

  if (unavailable) return <div className="mb-load-error" role="alert"><h3>The circuit cannot open here.</h3>
    <p>A Canvas drawing surface is unavailable. Try another browser to take a lap.</p></div>;
  const guidance = paused ? 'Take your time. The lap timer is paused.' : hud.offTrack
    ? 'Off the road. Ease off and steer back onto the circuit.' : !hud.lapStarted
      ? 'Hold W or the accelerator to get moving. The timer starts with your car.'
      : !hud.lapValid ? 'This lap cannot count as a best. Finish the loop or restart.'
        : hud.lastResultId > 0 && hud.elapsed < 5 ? announcement
          : 'Brake for tight corners. Follow the highlighted next checkpoint.';
  const progress = hud.checkpointIndex / (CHECKPOINT_COUNT - 1);
  return <div ref={hostRef} role="group" aria-label="Marina Bay driving game" onBlurCapture={(event) => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) controlsRef.current?.pause();
  }}>
    <div className="mb-board mb-board-playing">
      <div className="mb-stage">
        <canvas ref={canvasRef} tabIndex={0} aria-label="Marina Bay circuit. Drive with W A S D or arrow keys."
          aria-describedby="mb-driving-controls" onPointerDown={() => canvasRef.current?.focus({ preventScroll: true })}>
          Full Marina Bay circuit driving game. Use the controls below to accelerate, brake and steer.
        </canvas>
        {!hud.lapStarted && !paused && <p className="mb-game-hint">Hold W to accelerate · A / D to steer</p>}
        {paused && <div className="mb-pause-overlay"><strong>In the pits.</strong><p>Your lap is paused.</p>
          <button type="button" className="mb-button mb-button-primary" onClick={() => controlsRef.current?.resume()}>Resume lap</button></div>}
      </div>
      <div className="mb-touch-controls" role="group" aria-label="Hold driving controls">
        <div className="mb-touch-group">{touchButton('left', '←', 'Hold to steer left')}{touchButton('right', '→', 'Hold to steer right')}</div>
        <div className="mb-touch-group">{touchButton('brake', 'Brake', 'Hold to brake, then reverse')}{touchButton('throttle', 'Accelerate', 'Hold to accelerate')}</div>
      </div>
      <p className="mb-touch-help">Hold accelerate and a steering button together to turn.</p>
      <aside className="mb-pit-wall mb-telemetry" aria-label="Lap information">
        <div className="mb-session-status" data-paused={paused}><span>{paused ? 'SESSION PAUSED' : hud.lapStarted ? 'ON TRACK' : 'READY TO ROLL'}</span><span>LAP {hud.laps + 1}</span></div>
        <div><span className="mb-timer-label">Current lap</span><output className="mb-timer" aria-live="off">{formatLapTime(hud.elapsed)}</output></div>
        <dl className="mb-lap-records"><div><dt>Browser best</dt><dd>{formatLapTime(hud.bestLap)}</dd></div>
          <div><dt>Last lap</dt><dd>{formatLapTime(hud.lastLap)}{hud.lastLapValid === false && <span className="mb-small"> (invalid)</span>}</dd></div></dl>
        <div className="mb-speed-line"><strong>{Math.round(Math.abs(hud.speed) * 3.6)}</strong><span>KM/H{hud.speed < -0.1 ? ' · R' : ''}</span></div>
        <div><div className="mb-progress-label"><span>CHECKPOINTS</span><span>{hud.checkpointIndex} / {CHECKPOINT_COUNT - 1}</span></div>
          <div className="mb-progress" role="progressbar" aria-label="Lap checkpoints" aria-valuemin={0}
            aria-valuemax={CHECKPOINT_COUNT - 1} aria-valuenow={hud.checkpointIndex}><span style={{ width: `${progress * 100}%` }} /></div></div>
        <div className="mb-actions"><button type="button" className="mb-button" onClick={() => paused ? controlsRef.current?.resume() : controlsRef.current?.pause()}>{paused ? 'Resume' : 'Pause'} <kbd>P</kbd></button>
          <button type="button" className="mb-button" onClick={() => controlsRef.current?.restart()}>Restart <kbd>R</kbd></button></div>
        <p className="mb-message" data-warning={hud.offTrack || !hud.lapValid}>{guidance}</p>
        <p className="mb-small" id="mb-driving-controls">W / ↑ accelerate. S / ↓ brake, then reverse. A D / ← → steer. P pauses; R restarts. Tab leaves the game.</p>
        <p className="mb-sr-only" role="status" aria-live="polite" aria-atomic="true">{announcement}</p>
      </aside>
    </div>
  </div>;
}
