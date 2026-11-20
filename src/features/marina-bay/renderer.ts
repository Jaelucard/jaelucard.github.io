import type { GameState } from './simulation';
import { ROAD_HALF_WIDTH, TRACK, TRACK_VIEW, projectToTrack, sampleTrack } from './track';

const TURN_OFFSETS: readonly (readonly [number, number])[] = [
  [39, -8], [0, 39], [-8, -38], [-42, 4], [38, 5], [0, 40], [0, -39], [-40, 0], [0, -39],
  [-38, 0], [33, -29], [-39, 7], [3, 38], [45, 0], [0, 40], [34, -20], [-34, 25], [26, 26], [40, 0],
];

export function createRenderer(canvas: HTMLCanvasElement) {
  const context = canvas.getContext('2d', { alpha: false });
  if (!context) throw new Error('Canvas 2D is unavailable');
  const ctx: CanvasRenderingContext2D = context;
  const background = document.createElement('canvas');
  const backgroundContext = background.getContext('2d', { alpha: false });
  if (!backgroundContext) throw new Error('Canvas 2D is unavailable');
  const bg: CanvasRenderingContext2D = backgroundContext;
  let width = 1;
  let height = 1;
  let ratio = 1;
  let scale = 1;
  let offsetX = 0;
  let offsetY = 0;

  const route = new Path2D();
  TRACK.points.forEach((point, index) => {
    if (!index) route.moveTo(point.x, point.y);
    else route.lineTo(point.x, point.y);
  });
  route.closePath();

  function worldTransform(target: CanvasRenderingContext2D) {
    target.setTransform(ratio * scale, 0, 0, ratio * scale, ratio * offsetX, ratio * offsetY);
  }

  function text(label: string, x: number, y: number, size: number, color: string, align: CanvasTextAlign = 'left') {
    bg.font = `${size}px "IBM Plex Mono", monospace`;
    bg.fillStyle = color;
    bg.textAlign = align;
    bg.textBaseline = 'middle';
    bg.fillText(label, x, y);
  }

  function arrow(target: CanvasRenderingContext2D, s: number, color: string, size = 6) {
    const point = sampleTrack(s);
    target.save();
    target.translate(point.x, point.y);
    target.rotate(point.angle);
    target.beginPath();
    target.moveTo(-size, -size * .65);
    target.lineTo(size * .35, 0);
    target.lineTo(-size, size * .65);
    target.strokeStyle = color;
    target.lineWidth = 2;
    target.stroke();
    target.restore();
  }

  function drawScenery() {
    bg.fillStyle = '#111d20';
    bg.fillRect(TRACK_VIEW.x, TRACK_VIEW.y, TRACK_VIEW.width, TRACK_VIEW.height);
    bg.lineWidth = .8;
    bg.strokeStyle = '#203033';
    bg.beginPath();
    for (let x = -100; x < TRACK_VIEW.width; x += 70) { bg.moveTo(x, -125); bg.lineTo(x, 1050); }
    for (let y = -125; y < TRACK_VIEW.height; y += 70) { bg.moveTo(-115, y); bg.lineTo(1600, y); }
    bg.stroke();

    const water = new Path2D('M410 485 Q590 620 1060 710 L1600 800 L1600 1080 L310 1080 Q375 880 420 720Z');
    const waterGradient = bg.createLinearGradient(450, 500, 1200, 1000);
    waterGradient.addColorStop(0, '#16363a');
    waterGradient.addColorStop(1, '#10252f');
    bg.fillStyle = waterGradient;
    bg.fill(water);
    bg.strokeStyle = '#2c5355';
    bg.lineWidth = 2;
    bg.stroke(water);

    // Abstract city blocks and parks are decoration, not claimed geographic buildings.
    for (let row = 0; row < 10; row++) {
      for (let col = 0; col < 17; col++) {
        const x = col * 92 - 45;
        const y = row * 91 - 70;
        // Keep the top-left coordinate caption clear of decorative buildings.
        if (x < 260 && y < -20) continue;
        if (projectToTrack(x + 24, y + 18).distance < 70 || bg.isPointInPath(water,
          ratio * ((x + 24) * scale + offsetX), ratio * ((y + 18) * scale + offsetY))) continue;
        if ((row + col) % 4 === 0) {
          bg.fillStyle = '#203b33';
          for (let k = 0; k < 4; k++) {
            bg.beginPath(); bg.arc(x + k * 12, y + (k % 2) * 12, 7, 0, Math.PI * 2); bg.fill();
          }
        } else {
          const w = 30 + ((row * 7 + col) % 3) * 9;
          const h = 29 + ((row + col * 5) % 3) * 7;
          bg.fillStyle = '#0c171b'; bg.fillRect(x + 5, y + 6, w, h);
          bg.fillStyle = '#253135'; bg.strokeStyle = '#394345'; bg.lineWidth = 1;
          bg.fillRect(x, y, w, h); bg.strokeRect(x, y, w, h);
          bg.fillStyle = '#8d876547';
          for (let windowX = x + 6; windowX < x + w - 2; windowX += 10) bg.fillRect(windowX, y + 6, 3, 4);
        }
      }
    }

    // Singapore Flyer illustration inside the final part of the circuit.
    bg.save(); bg.translate(1267, 550);
    bg.strokeStyle = '#7c9c92'; bg.lineWidth = 2;
    bg.beginPath(); bg.arc(0, 0, 43, 0, Math.PI * 2); bg.stroke();
    for (let i = 0; i < 12; i++) {
      const angle = i * Math.PI / 6;
      bg.beginPath(); bg.moveTo(0, 0); bg.lineTo(Math.cos(angle) * 43, Math.sin(angle) * 43); bg.stroke();
      bg.fillStyle = '#e4d6aa'; bg.beginPath(); bg.arc(Math.cos(angle) * 43, Math.sin(angle) * 43, 2, 0, Math.PI * 2); bg.fill();
    }
    bg.beginPath(); bg.moveTo(-20, 53); bg.lineTo(0, 0); bg.lineTo(20, 53); bg.stroke();
    bg.restore();
    text('SINGAPORE FLYER', 1267, 626, 11, '#8ca7a1', 'center');

    bg.fillStyle = '#293235'; bg.fillRect(1470, 250, 30, 220);
    bg.strokeStyle = '#6c756a'; bg.lineWidth = 1;
    for (let y = 257; y < 464; y += 14) { bg.beginPath(); bg.moveTo(1473, y); bg.lineTo(1497, y); bg.stroke(); }
    bg.save(); bg.translate(1521, 360); bg.rotate(Math.PI / 2);
    text('PIT BUILDING', 0, 0, 12, '#a7afa2', 'center'); bg.restore();

    // Quiet skyline vignette below the route, including three linked towers.
    bg.fillStyle = '#294049';
    for (let i = 0; i < 13; i++) {
      const buildingHeight = 17 + (i * 17 % 39);
      bg.fillRect(970 + i * 28, 1010 - buildingHeight, 19, buildingHeight);
    }
    bg.fillStyle = '#41575a';
    [850, 880, 910].forEach((x) => bg.fillRect(x, 953, 15, 57));
    bg.beginPath(); bg.moveTo(837, 954); bg.quadraticCurveTo(880, 936, 935, 951); bg.lineTo(926, 959); bg.lineTo(847, 960); bg.closePath(); bg.fill();
    text('MARINA BAY', 800, 820, 25, '#6b939a', 'center');
    text('01°17′ N / 103°51′ E', 0, -65, 14, '#9aadaa');
    text('SINGAPORE AFTER DARK', 1420, 1008, 13, '#829c9c', 'right');
  }

  function drawTrack() {
    bg.lineJoin = 'round';
    bg.lineCap = 'round';
    bg.strokeStyle = '#050c11'; bg.lineWidth = ROAD_HALF_WIDTH * 2 + 15; bg.stroke(route);
    bg.strokeStyle = '#8f9a94'; bg.lineWidth = ROAD_HALF_WIDTH * 2 + 4; bg.stroke(route);
    bg.strokeStyle = '#dc3847'; bg.setLineDash([12, 12]); bg.stroke(route); bg.setLineDash([]);
    bg.strokeStyle = '#344247'; bg.lineWidth = ROAD_HALF_WIDTH * 2; bg.stroke(route);
    bg.strokeStyle = '#3d4c51'; bg.lineWidth = ROAD_HALF_WIDTH * 1.2; bg.stroke(route);
    bg.strokeStyle = '#a1b7ae65'; bg.lineWidth = 1.2; bg.setLineDash([8, 18]); bg.stroke(route); bg.setLineDash([]);
    for (let s = 80; s < TRACK.length; s += 180) arrow(bg, s, '#c0d5c483', 6);

    TRACK.turns.forEach((turn, index) => {
      const point = sampleTrack(turn.progress * TRACK.length);
      const [dx, dy] = TURN_OFFSETS[index];
      text(String(turn.number).padStart(2, '0'), point.x + dx, point.y + dy,
        Math.max(12, 7 / scale), '#b2c1b9', 'center');
    });

    const startPoint = sampleTrack(0);
    bg.save(); bg.translate(startPoint.x, startPoint.y); bg.rotate(startPoint.angle);
    const checkerHeight = ROAD_HALF_WIDTH / 4;
    for (let row = 0; row < 8; row++) for (let col = 0; col < 2; col++) {
      bg.fillStyle = (row + col) % 2 ? '#132126' : '#f3eee0';
      bg.fillRect(-4 + col * 4, -ROAD_HALF_WIDTH + row * checkerHeight, 4, checkerHeight);
    }
    bg.restore();
    text('START', 1312, startPoint.y - 8, 11, '#d9d8c6', 'center');
    text('FINISH', 1312, startPoint.y + 8, 11, '#b9cac5', 'center');
  }

  function resize() {
    width = Math.max(1, canvas.clientWidth);
    height = Math.max(1, canvas.clientHeight);
    ratio = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    background.width = canvas.width;
    background.height = canvas.height;
    scale = Math.min(width / TRACK_VIEW.width, height / TRACK_VIEW.height);
    offsetX = (width - TRACK_VIEW.width * scale) / 2 - TRACK_VIEW.x * scale;
    offsetY = (height - TRACK_VIEW.height * scale) / 2 - TRACK_VIEW.y * scale;
    bg.setTransform(1, 0, 0, 1, 0, 0);
    bg.fillStyle = '#111d20'; bg.fillRect(0, 0, background.width, background.height);
    worldTransform(bg);
    drawScenery(); drawTrack();
  }

  function draw(state: GameState) {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.drawImage(background, 0, 0);
    worldTransform(ctx);
    // A small marker shows the next gate without obstructing the full map.
    const next = sampleTrack(state.nextCheckpoint);
    ctx.save(); ctx.translate(next.x, next.y); ctx.rotate(next.angle);
    ctx.strokeStyle = '#b6e4c56b'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(0, -ROAD_HALF_WIDTH); ctx.lineTo(0, ROAD_HALF_WIDTH); ctx.stroke();
    ctx.restore();

    ctx.save(); ctx.translate(state.x, state.y); ctx.rotate(state.heading);
    // Keep the car legible on a phone while physics remains in world units.
    const carScale = Math.max(1, 13 / (25 * scale));
    ctx.scale(carScale, carScale);
    ctx.strokeStyle = state.offTrack ? '#f4b45c80' : '#f4f0d440'; ctx.lineWidth = 1 / carScale;
    ctx.beginPath(); ctx.arc(0, 0, 22, 0, Math.PI * 2); ctx.stroke();
    ctx.fillStyle = '#060d12';
    ctx.fillRect(-10, -10, 7, 5); ctx.fillRect(-10, 5, 7, 5);
    ctx.save(); ctx.translate(8, -8); ctx.rotate(state.steering * .3); ctx.fillRect(-3, -2, 6, 4); ctx.restore();
    ctx.save(); ctx.translate(8, 8); ctx.rotate(state.steering * .3); ctx.fillRect(-3, -2, 6, 4); ctx.restore();
    ctx.fillStyle = '#ee2440';
    ctx.beginPath(); ctx.moveTo(14, 0); ctx.lineTo(5, -4); ctx.lineTo(-10, -6); ctx.lineTo(-13, -4); ctx.lineTo(-13, 4); ctx.lineTo(-10, 6); ctx.lineTo(5, 4); ctx.closePath(); ctx.fill();
    ctx.fillRect(-12, -9, 3, 18); ctx.fillRect(10, -8, 3, 16);
    ctx.fillStyle = '#faf1dd'; ctx.fillRect(1, -2, 8, 4);
    ctx.fillStyle = '#12222a'; ctx.beginPath(); ctx.ellipse(-3, 0, 4, 2.6, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#f1ce79'; ctx.beginPath(); ctx.arc(-3, 0, 1.7, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  }

  resize();
  return { draw, resize, destroy() { background.width = 1; background.height = 1; } };
}
