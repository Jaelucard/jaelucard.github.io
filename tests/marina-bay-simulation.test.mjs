import assert from 'node:assert/strict';
import test from 'node:test';
import {
  CHECKPOINT_COUNT, INPUT_IDLE, MAX_REVERSE_SPEED, MAX_SPEED,
  createGame, formatLapTime, resetGame, updateGame,
} from '../src/features/marina-bay/simulation.ts';
import { ROAD_HALF_WIDTH, TRACK, projectToTrack, sampleTrack } from '../src/features/marina-bay/track.ts';

const throttle = { ...INPUT_IDLE, throttle: true };
const brake = { ...INPUT_IDLE, brake: true };
const tick = (state, input, seconds, rate = 120) => {
  for (let i = 0; i < Math.round(seconds * rate); i++) updateGame(state, input, 1 / rate);
};

// Replay a measured full-route trajectory. Each simulated movement still crosses
// the real gates in the real direction; steering is supplied by the route fixture.
function replayRoute(state, { skipFrom = Infinity, skipTo = Infinity } = {}) {
  for (let distance = 2; distance < TRACK.length + 3; distance += 1) {
    if (distance >= skipFrom && distance < skipTo) continue;
    const point = sampleTrack(distance);
    const ahead = sampleTrack(distance + 1.01);
    state.x = point.x;
    state.y = point.y;
    state.heading = Math.atan2(ahead.y - point.y, ahead.x - point.x);
    state.speed = 60;
    state.steering = 0;
    updateGame(state, throttle, 1 / 60);
  }
}

test('the car starts on the full circuit, stationary and aligned in the race direction', () => {
  const state = createGame();
  const start = sampleTrack(2);
  assert.equal(state.x, start.x);
  assert.equal(state.y, start.y);
  assert.equal(state.heading, start.angle);
  assert.equal(state.speed, 0);
  assert.equal(state.nextCheckpoint, TRACK.length / CHECKPOINT_COUNT);
  assert.equal(state.lapStarted, false);
  assert.ok(Math.abs(TRACK.length - 4927) < 1e-6);
});

test('waiting or steering at rest does not rotate the car or start its timer', () => {
  const state = createGame();
  const initialHeading = state.heading;
  tick(state, { ...INPUT_IDLE, right: true }, 5);
  assert.ok(Math.abs(state.heading - initialHeading) < 1e-10);
  assert.equal(state.speed, 0);
  assert.equal(state.elapsed, 0);
  assert.equal(state.lapStarted, false);
});

test('acceleration is gradual and bounded, and braking reaches a slow capped reverse', () => {
  const state = createGame();
  tick(state, throttle, 0.5);
  assert.ok(state.speed > 10 && state.speed < 20);
  assert.equal(state.lapStarted, true);
  tick(state, throttle, 2.5);
  assert.equal(state.speed, MAX_SPEED);
  tick(state, brake, 1.2);
  assert.ok(state.speed < 5 && state.speed > -2);
  tick(state, brake, 3);
  assert.ok(state.speed >= -MAX_REVERSE_SPEED && state.speed < -9);
});

test('steering and timing agree across 30 fps and 120 fps render updates', () => {
  const slower = createGame();
  const faster = createGame();
  const input = { ...throttle, right: true };
  tick(slower, input, 3, 30);
  tick(faster, input, 3, 120);
  for (const field of ['x', 'y', 'speed', 'heading', 'steering', 'elapsed']) {
    assert.ok(Math.abs(slower[field] - faster[field]) < 1e-8, `${field} differs`);
  }
});

test('leaving the road slows the car even while accelerating and stays recoverable', () => {
  const state = createGame();
  const position = sampleTrack(1100);
  state.x = position.x - Math.sin(position.angle) * (ROAD_HALF_WIDTH + 12);
  state.y = position.y + Math.cos(position.angle) * (ROAD_HALF_WIDTH + 12);
  state.heading = position.angle;
  state.speed = 60;
  assert.ok(projectToTrack(state.x, state.y).distance > ROAD_HALF_WIDTH);
  tick(state, throttle, 2);
  assert.ok(state.speed <= 20, `off-track speed ${state.speed}`);
  assert.equal(state.offTrack, true);
  assert.ok(projectToTrack(state.x, state.y).distance <= ROAD_HALF_WIDTH + 15.01);
  assert.equal(Number.isFinite(state.x + state.y + state.heading), true);
});

test('a wide line inside the soft boundary still passes its checkpoint', () => {
  const state = createGame();
  const gateIndex = 15;
  const gateDistance = gateIndex * TRACK.length / CHECKPOINT_COUNT;
  const position = sampleTrack(gateDistance - 2);
  // This line is outside the asphalt but inside the recoverable boundary.
  // The car should lose speed, not silently invalidate an otherwise complete lap.
  const offset = ROAD_HALF_WIDTH + 12;
  Object.assign(state, {
    x: position.x - Math.sin(position.angle) * offset,
    y: position.y + Math.cos(position.angle) * offset,
    heading: position.angle, speed: 50, elapsed: 30, lapStarted: true,
    checkpointIndex: gateIndex - 1, nextCheckpoint: gateDistance,
  });
  updateGame(state, INPUT_IDLE, 0.1);
  assert.equal(state.offTrack, true);
  assert.ok(state.speed < 50);
  assert.equal(state.checkpointIndex, gateIndex);
  assert.equal(state.lapValid, true);
});

test('a controller can physically drive the entire circuit and record a clean lap', () => {
  const state = createGame();
  const wrappedAngle = (angle) => Math.atan2(Math.sin(angle), Math.cos(angle));
  let offTrackFrames = 0;
  // This controller only presses the same four buttons as the player. It never
  // changes the car's position, heading, speed or checkpoint state directly.
  for (let frame = 0; frame < 180 * 120 && state.lastResultId === 0; frame++) {
    const position = projectToTrack(state.x, state.y);
    const lookAhead = Math.max(12, Math.abs(state.speed) * 0.45);
    const target = sampleTrack(position.s + lookAhead);
    const turn = wrappedAngle(Math.atan2(target.y - state.y, target.x - state.x) - state.heading);
    const curvature = Math.abs(wrappedAngle(sampleTrack(position.s + 35).angle - position.angle));
    const targetSpeed = curvature > 0.6 ? 20 : curvature > 0.25 ? 35 : 62;
    updateGame(state, {
      throttle: state.speed < targetSpeed,
      brake: state.speed > targetSpeed + 2,
      left: turn < -0.025,
      right: turn > 0.025,
    }, 1 / 120);
    if (state.offTrack) offTrackFrames++;
  }
  assert.equal(state.lastResultId, 1);
  assert.equal(state.laps, 1);
  assert.equal(state.lastLapValid, true);
  assert.ok(state.lastLap > 90 && state.lastLap < 150, `lap time ${state.lastLap}`);
  assert.equal(offTrackFrames, 0);
  assert.equal(state.bestLap, state.lastLap);
  assert.equal(state.checkpointIndex, 0);
  assert.ok(state.elapsed < 0.1);
});

test('skipping a portion of the circuit cannot create a valid lap or personal best', () => {
  const state = createGame();
  replayRoute(state, { skipFrom: 400, skipTo: 900 });
  assert.equal(state.lastResultId, 1);
  assert.equal(state.lastLapValid, false);
  assert.equal(state.laps, 0);
  assert.equal(state.bestLap, null);
  assert.equal(state.checkpointIndex, 0);
});

test('crossing the finish in reverse does not count, even after all checkpoints', () => {
  const state = createGame();
  const position = sampleTrack(1);
  Object.assign(state, {
    x: position.x, y: position.y, heading: position.angle + Math.PI,
    speed: 40, lapStarted: true, elapsed: 100,
    checkpointIndex: CHECKPOINT_COUNT - 1, distanceDriven: TRACK.length,
  });
  updateGame(state, INPUT_IDLE, 0.1);
  assert.equal(state.lastResultId, 0);
  assert.equal(state.laps, 0);
  assert.equal(state.bestLap, null);
});

test('crossing the finish without checkpoints restarts the attempt without a record', () => {
  const state = createGame(95);
  const position = sampleTrack(TRACK.length - 1);
  Object.assign(state, {
    x: position.x, y: position.y, heading: position.angle,
    speed: 40, lapStarted: true, elapsed: 70, distanceDriven: TRACK.length,
  });
  updateGame(state, INPUT_IDLE, 0.1);
  assert.equal(state.lastResultId, 1);
  assert.equal(state.lastLapValid, false);
  assert.equal(state.bestLap, 95);
  assert.equal(state.checkpointIndex, 0);
  assert.ok(state.elapsed < 0.1);
});

test('a restart clears motion and current progress but preserves completed results', () => {
  const state = createGame(95);
  Object.assign(state, { speed: 30, elapsed: 25, lapStarted: true, laps: 2,
    lastLap: 97, lastLapValid: true, lastResultId: 2, checkpointIndex: 15 });
  resetGame(state);
  assert.equal(state.speed, 0);
  assert.equal(state.elapsed, 0);
  assert.equal(state.lapStarted, false);
  assert.equal(state.checkpointIndex, 0);
  assert.equal(state.bestLap, 95);
  assert.equal(state.laps, 2);
  assert.equal(state.lastLap, 97);
  assert.equal(state.lastResultId, 2);
});

test('invalid deltas do nothing and a stale background-tab delta cannot teleport the car', () => {
  const state = createGame();
  const initial = structuredClone(state);
  for (const delta of [NaN, Infinity, -1, 0]) updateGame(state, throttle, delta);
  assert.deepEqual(state, initial);
  updateGame(state, throttle, 100);
  assert.ok(state.elapsed <= 0.250001);
  assert.ok(Math.hypot(state.x - initial.x, state.y - initial.y) < MAX_SPEED * 0.25);
});

test('stored best times are validated and the timer consistently formats milliseconds', () => {
  for (const value of [NaN, Infinity, -10, 0, 1]) assert.equal(createGame(value).bestLap, null);
  assert.equal(createGame(97.123).bestLap, 97.123);
  assert.equal(formatLapTime(97.123), '01:37.123');
  assert.equal(formatLapTime(0), '00:00.000');
  assert.equal(formatLapTime(60), '01:00.000');
  assert.equal(formatLapTime(null), '--:--.---');
  assert.equal(formatLapTime(NaN), '--:--.---');
});
