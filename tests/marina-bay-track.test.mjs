import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { SOURCE_POINTS, TURN_ANCHORS } from '../src/features/marina-bay/track-data.ts';
import { OFFICIAL_LENGTH, TRACK, projectToTrack, sampleTrack } from '../src/features/marina-bay/track.ts';

const geojson = JSON.parse(readFileSync(new URL('../public/assets/marina-bay/marina-bay-source.geojson', import.meta.url), 'utf8'));
const source = geojson.features[0].geometry.coordinates;
const uniqueSource = source.slice(0, -1);
const meanLatitude = uniqueSource.reduce((sum, point) => sum + point[1], 0) / uniqueSource.length;
const minLongitude = Math.min(...source.map(([longitude]) => longitude));
const maxLatitude = Math.max(...source.map(([, latitude]) => latitude));
const eastFactor = Math.cos(meanLatitude * Math.PI / 180);
// This reference is derived from the distributed upstream GeoJSON, independently
// of the generated coordinates. A single fitted scale must explain both axes.
const geographicPoints = source.map(([longitude, latitude]) => ({
  x: (longitude - minLongitude) * eastFactor,
  y: maxLatitude - latitude,
}));
const commonScale = TRACK.width / Math.max(...geographicPoints.map(({ x }) => x));
const referencePoint = (sourceIndex) => ({
  x: geographicPoints[sourceIndex].x * commonScale,
  y: geographicPoints[sourceIndex].y * commonScale,
});
const raceSourceIndexes = [0, ...Array.from({ length: source.length - 2 }, (_, index) => source.length - 2 - index), 0];
const near = (actual, expected, tolerance = 0.0002) => assert.ok(
  Math.abs(actual - expected) <= tolerance, `${actual} differs from ${expected}`,
);
const nearPoint = (actual, expected, tolerance) => {
  near(actual.x, expected.x, tolerance);
  near(actual.y, expected.y, tolerance);
};
const cyclicDistance = (a, b) => Math.min(Math.abs(a - b), Math.abs(a - b + TRACK.length), Math.abs(a - b - TRACK.length));

test('the complete 116-vertex upstream route is retained in race order without stretching either axis', () => {
  assert.equal(geojson.features[0].geometry.type, 'LineString');
  assert.equal(source.length, 116);
  assert.equal(SOURCE_POINTS.length, source.length);
  assert.equal(TRACK.points.length, source.length);
  assert.deepEqual(source.at(-1), source[0]);
  TRACK.points.forEach((point, index) => nearPoint(point, referencePoint(raceSourceIndexes[index])));
  // Explicitly retain the long post-2023 waterfront straight, rather than
  // accidentally restoring the former Turns 16-19 detour.
  const straightStart = raceSourceIndexes.indexOf(22);
  assert.equal(raceSourceIndexes[straightStart + 1], 21);
  assert.ok(Math.hypot(
    TRACK.points[straightStart + 1].x - TRACK.points[straightStart].x,
    TRACK.points[straightStart + 1].y - TRACK.points[straightStart].y,
  ) > 280);
});

test('the loop closes at the main straight, starts northbound, and has a uniform 4927 m game scale', () => {
  nearPoint(TRACK.points.at(-1), TRACK.points[0], 1e-10);
  near(TRACK.length, OFFICIAL_LENGTH, 1e-8);
  assert.equal(OFFICIAL_LENGTH, 4927);
  near(TRACK.points[0].s, 0, 1e-10);
  let measuredLength = 0;
  let signedArea = 0;
  for (let index = 1; index < TRACK.points.length; index++) {
    const previous = TRACK.points[index - 1];
    const point = TRACK.points[index];
    const segment = Math.hypot(point.x - previous.x, point.y - previous.y);
    assert.ok(segment > 0, `duplicate vertex at ${index}`);
    assert.ok(point.s > previous.s, `non-increasing distance at ${index}`);
    near(point.s - previous.s, segment, 1e-8);
    measuredLength += segment;
    signedArea += previous.x * point.y - point.x * previous.y;
  }
  near(measuredLength, 4927, 1e-8);
  assert.ok(signedArea < 0, 'race direction is anticlockwise in screen coordinates');
  const start = sampleTrack(0);
  assert.ok(Math.sin(start.angle) < -0.98, 'the first straight must head north toward Turn 1');
  assert.ok(sampleTrack(100).y < start.y);
});

test('all 19 turn labels are ordered and retain the reviewed FIA-map anchor locations', () => {
  // Approximate visual anchors, not surveyed apex coordinates. In particular,
  // 11 and 12 mark the short left/right sequence before the Turn 13 hairpin.
  const sourceTurnIndexes = [111, 108, 102, 95, 88, 84, 80, 75, 70, 62, 55, 52, 40, 30, 24, 18, 14, 8, 3];
  assert.equal(TURN_ANCHORS.length, 19);
  assert.deepEqual(TURN_ANCHORS.map(({ number }) => number), Array.from({ length: 19 }, (_, i) => i + 1));
  TURN_ANCHORS.forEach((turn, index) => {
    assert.ok(turn.progress > 0 && turn.progress < 1);
    if (index) assert.ok(turn.progress > TURN_ANCHORS[index - 1].progress);
    // Progress fractions are intentionally stored to six decimal places.
    nearPoint(sampleTrack(turn.progress * TRACK.length), referencePoint(sourceTurnIndexes[index]), 0.003);
  });
});

test('sampling wraps seamlessly for positive and negative distances and traverses every segment', () => {
  for (const distance of [0, 1, 123.45, 2000, TRACK.length - 0.01]) {
    const expected = sampleTrack(distance);
    for (const laps of [-3, -1, 0, 1, 3]) {
      const actual = sampleTrack(distance + laps * TRACK.length);
      nearPoint(actual, expected, 1e-8);
      near(actual.angle, expected.angle, 1e-8);
    }
  }
  for (let index = 0; index < TRACK.points.length - 1; index++) {
    const a = TRACK.points[index];
    const b = TRACK.points[index + 1];
    nearPoint(sampleTrack((a.s + b.s) / 2), { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }, 1e-8);
  }
});

test('projection recovers route progress and perpendicular road distance without jumping nearby segments', () => {
  for (const distance of [100, 1200, 2600, 3900, 4800]) {
    const point = sampleTrack(distance);
    const onTrack = projectToTrack(point.x, point.y);
    near(onTrack.distance, 0, 1e-8);
    assert.ok(cyclicDistance(onTrack.s, distance) < 1e-7);
    for (const offset of [-9, 9]) {
      const projection = projectToTrack(point.x - Math.sin(point.angle) * offset, point.y + Math.cos(point.angle) * offset);
      near(projection.distance, Math.abs(offset), 1e-7);
      nearPoint(projection, point, 1e-7);
      assert.ok(cyclicDistance(projection.s, distance) < 1e-7);
    }
  }
  const atClosure = projectToTrack(TRACK.points[0].x, TRACK.points[0].y);
  assert.ok(cyclicDistance(atClosure.s, 0) < 1e-8);
});
