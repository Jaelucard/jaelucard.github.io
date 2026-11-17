import { TRACK, ROAD_HALF_WIDTH, sampleTrack, projectToTrack } from './track.ts';

/** World distances are metres; speeds are metres per second; angles are radians. */
export const MAX_SPEED = 72;
export const MAX_REVERSE_SPEED = 10;
export const CHECKPOINT_COUNT = 64;
export const SIMULATION_STEP = 1 / 120;
const CHECKPOINT_SPACING = TRACK.length / CHECKPOINT_COUNT;
export const MIN_LAP_TIME = TRACK.length / MAX_SPEED * 0.75;
const OFF_TRACK_SPEED = 19;
const SOFT_BOUNDARY_DISTANCE = ROAD_HALF_WIDTH + 15;
const TAU = Math.PI * 2;

export type InputState = {
  throttle: boolean;
  brake: boolean;
  left: boolean;
  right: boolean;
};

export const INPUT_IDLE: Readonly<InputState> = {
  throttle: false, brake: false, left: false, right: false,
};

export type GameState = {
  x: number;
  y: number;
  heading: number;
  speed: number;
  steering: number;
  elapsed: number;
  lapStarted: boolean;
  /** Number of valid completed laps in this session. */
  laps: number;
  lastLap: number | null;
  lastLapValid: boolean | null;
  /** Changes on every finish crossing, including a lap with missed checkpoints. */
  lastResultId: number;
  bestLap: number | null;
  /** Passed interior gates, from 0 to 63. Gate 64 is the finish line. */
  checkpointIndex: number;
  /** Distance along the circuit to the next gate, in metres. */
  nextCheckpoint: number;
  lapValid: boolean;
  offTrack: boolean;
  /** Current nearest position along the full circuit, from 0 to 1. */
  progress: number;
  distanceDriven: number;
};

type Point = { x: number; y: number };
type Gate = Point & { tx: number; ty: number; s: number };

const GATES: Gate[] = Array.from({ length: CHECKPOINT_COUNT }, (_, index) => {
  const s = index * CHECKPOINT_SPACING;
  const point = sampleTrack(s);
  return { ...point, s, tx: Math.cos(point.angle), ty: Math.sin(point.angle) };
});

function validBest(value: number | null | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= MIN_LAP_TIME
    ? value : null;
}

export function createGame(bestLap: number | null = null): GameState {
  const start = sampleTrack(2);
  return {
    x: start.x, y: start.y, heading: start.angle, speed: 0, steering: 0,
    elapsed: 0, lapStarted: false, laps: 0, lastLap: null, lastLapValid: null,
    lastResultId: 0, bestLap: validBest(bestLap), checkpointIndex: 0,
    nextCheckpoint: CHECKPOINT_SPACING, lapValid: true, offTrack: false,
    progress: 2 / TRACK.length, distanceDriven: 0,
  };
}

/** Restart the attempt while retaining the session's results and personal best. */
export function resetGame(state: GameState): void {
  const { bestLap, laps, lastLap, lastLapValid, lastResultId } = state;
  Object.assign(state, createGame(bestLap), { laps, lastLap, lastLapValid, lastResultId });
}

export function formatLapTime(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds) || seconds < 0) return '--:--.---';
  const milliseconds = Math.floor(seconds * 1000);
  const minutes = Math.floor(milliseconds / 60_000);
  const wholeSeconds = Math.floor(milliseconds / 1000) % 60;
  const fraction = milliseconds % 1000;
  return `${String(minutes).padStart(2, '0')}:${String(wholeSeconds).padStart(2, '0')}.${String(fraction).padStart(3, '0')}`;
}

function approach(value: number, target: number, amount: number): number {
  return value < target ? Math.min(value + amount, target) : Math.max(value - amount, target);
}

/** Find a forward, road-width crossing. A nearby parallel road cannot claim this gate. */
function gateCrossing(from: Point, to: Point, gate: Gate): number | null {
  const before = (from.x - gate.x) * gate.tx + (from.y - gate.y) * gate.ty;
  const after = (to.x - gate.x) * gate.tx + (to.y - gate.y) * gate.ty;
  if (before >= 0 || after < 0) return null;
  const fraction = before / (before - after);
  const x = from.x + (to.x - from.x) * fraction;
  const y = from.y + (to.y - from.y) * fraction;
  const across = Math.abs(-(x - gate.x) * gate.ty + (y - gate.y) * gate.tx);
  // A car brushing the soft boundary still completes this gate. Slowdown is
  // the penalty for a wide line; a small excursion must not silently lose a lap.
  if (across > SOFT_BOUNDARY_DISTANCE + 1) return null;
  const projection = projectToTrack(x, y);
  const difference = Math.abs(projection.s - gate.s);
  if (Math.min(difference, TRACK.length - difference) > CHECKPOINT_SPACING * 0.6) return null;
  return fraction;
}

function finishLap(state: GameState, fraction: number, dt: number, travelled: number): void {
  const carriedTime = dt * (1 - fraction);
  const time = Math.max(0, state.elapsed - carriedTime);
  const carriedDistance = travelled * (1 - fraction);
  const valid = state.lapValid && state.checkpointIndex === CHECKPOINT_COUNT - 1
    && time >= MIN_LAP_TIME && state.distanceDriven - carriedDistance >= TRACK.length * 0.8;

  state.lastLap = time;
  state.lastLapValid = valid;
  state.lastResultId += 1;
  if (valid) {
    state.laps += 1;
    if (state.bestLap === null || time < state.bestLap) state.bestLap = time;
  }
  state.elapsed = carriedTime;
  state.distanceDriven = carriedDistance;
  state.checkpointIndex = 0;
  state.nextCheckpoint = CHECKPOINT_SPACING;
  state.lapValid = true;
}

function step(state: GameState, input: Readonly<InputState>, dt: number): void {
  const from = { x: state.x, y: state.y };
  const road = projectToTrack(state.x, state.y);
  state.offTrack = road.distance > ROAD_HALF_WIDTH;

  // Both pedals act as a brake. Reversing requires braking all the way to a stop.
  if (input.brake) {
    if (state.speed > 0) state.speed = Math.max(0, state.speed - 58 * dt);
    else if (!input.throttle) state.speed = Math.max(-MAX_REVERSE_SPEED, state.speed - 12 * dt);
  } else if (input.throttle) {
    state.speed += (state.speed < 0 ? 45 : 30) * dt;
  } else {
    state.speed = approach(state.speed, 0, 3 * dt);
  }

  state.speed = approach(state.speed, 0, state.speed * state.speed * 0.0013 * dt);
  state.speed = Math.max(-MAX_REVERSE_SPEED, Math.min(MAX_SPEED, state.speed));
  if (state.offTrack && state.speed > OFF_TRACK_SPEED) {
    state.speed = Math.max(OFF_TRACK_SPEED, state.speed - 68 * dt);
  }

  const steeringTarget = Number(input.right) - Number(input.left);
  state.steering += (steeringTarget - state.steering) * (1 - Math.exp(-10 * dt));
  const speedFraction = Math.min(Math.abs(state.speed) / MAX_SPEED, 1);
  const steeringAtSpeed = Math.min(Math.abs(state.speed) / 12, 1);
  const turnRate = (2.5 - 1.2 * speedFraction) * steeringAtSpeed;
  state.heading += state.steering * turnRate * Math.sign(state.speed) * dt;
  state.heading = ((state.heading + Math.PI) % TAU + TAU) % TAU - Math.PI;
  state.x += Math.cos(state.heading) * state.speed * dt;
  state.y += Math.sin(state.heading) * state.speed * dt;

  const projected = projectToTrack(state.x, state.y);
  // A soft outer boundary keeps an accidental excursion visible and recoverable.
  // The car retains its heading, so steering back onto the road remains meaningful.
  const outerLimit = SOFT_BOUNDARY_DISTANCE;
  if (projected.distance > outerLimit) {
    const scale = outerLimit / projected.distance;
    state.x = projected.x + (state.x - projected.x) * scale;
    state.y = projected.y + (state.y - projected.y) * scale;
    state.speed = approach(state.speed, 0, 85 * dt);
  }
  state.offTrack = projected.distance > ROAD_HALF_WIDTH;
  state.progress = projected.s / TRACK.length;

  if (!state.lapStarted && Math.abs(state.speed) > 0.15) state.lapStarted = true;
  if (!state.lapStarted) return;

  const travelled = Math.hypot(state.x - from.x, state.y - from.y);
  state.elapsed += dt;
  state.distanceDriven += travelled;
  const next = (state.checkpointIndex + 1) % CHECKPOINT_COUNT;
  if (next !== 0 && gateCrossing(from, state, GATES[next]) !== null) {
    state.checkpointIndex += 1;
    state.nextCheckpoint = (state.checkpointIndex + 1) * CHECKPOINT_SPACING;
  }
  const finish = gateCrossing(from, state, GATES[0]);
  if (finish !== null && state.elapsed > 3) finishLap(state, finish, dt, travelled);
}

/**
 * The host pauses by not calling this function. Small deterministic steps make
 * steering and timing independent of rendering frequency; stale tab deltas are capped.
 */
export function updateGame(state: GameState, input: Readonly<InputState>, delta: number): void {
  if (!Number.isFinite(delta) || delta <= 0) return;
  let remaining = Math.min(delta, 0.25);
  while (remaining > 1e-9) {
    const dt = Math.min(remaining, SIMULATION_STEP);
    step(state, input, dt);
    remaining -= dt;
  }
}
