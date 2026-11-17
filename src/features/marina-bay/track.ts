import { SOURCE_POINTS, TURN_ANCHORS } from './track-data.ts';

export type TrackPoint = { x: number; y: number; s: number };
export type TrackSample = { x: number; y: number; angle: number };

export const OFFICIAL_LENGTH = 4927;
// Arcade road width is deliberately generous; the complete centreline is preserved.
export const ROAD_HALF_WIDTH = 18;
const sourceLength = SOURCE_POINTS.slice(1).reduce((total, point, i) =>
  total + Math.hypot(point[0] - SOURCE_POINTS[i][0], point[1] - SOURCE_POINTS[i][1]), 0);
const scale = OFFICIAL_LENGTH / sourceLength;
let distance = 0;
const points: TrackPoint[] = SOURCE_POINTS.map(([x, y], i) => {
  if (i) distance += Math.hypot(x - SOURCE_POINTS[i - 1][0], y - SOURCE_POINTS[i - 1][1]) * scale;
  return { x: x * scale, y: y * scale, s: distance };
});

export const TRACK = {
  points,
  length: distance,
  width: Math.max(...points.map((p) => p.x)),
  height: Math.max(...points.map((p) => p.y)),
  turns: TURN_ANCHORS,
};

export function sampleTrack(s: number): TrackSample {
  let wrapped = ((s % TRACK.length) + TRACK.length) % TRACK.length;
  // Canonicalise the seam after floating-point modulo, including negative laps.
  if (wrapped < 1e-8 || TRACK.length - wrapped < 1e-8) wrapped = 0;
  let lo = 0;
  let hi = points.length - 2;
  while (lo < hi) {
    const middle = Math.ceil((lo + hi) / 2);
    if (points[middle].s <= wrapped) lo = middle;
    else hi = middle - 1;
  }
  const a = points[lo];
  const b = points[lo + 1];
  const fraction = (wrapped - a.s) / (b.s - a.s);
  return { x: a.x + (b.x - a.x) * fraction, y: a.y + (b.y - a.y) * fraction,
    angle: Math.atan2(b.y - a.y, b.x - a.x) };
}

export function projectToTrack(x: number, y: number) {
  let best = { x: points[0].x, y: points[0].y, s: 0, distance: Infinity, angle: 0 };
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i];
    const b = points[i + 1];
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const t = Math.max(0, Math.min(1, ((x - a.x) * dx + (y - a.y) * dy) / (dx * dx + dy * dy)));
    const px = a.x + t * dx;
    const py = a.y + t * dy;
    const d = Math.hypot(x - px, y - py);
    if (d < best.distance) best = { x: px, y: py, s: a.s + t * (b.s - a.s), distance: d, angle: Math.atan2(dy, dx) };
  }
  return best;
}

export const TRACK_VIEW = { x: -115, y: -125, width: TRACK.width + 270, height: TRACK.height + 235 };
