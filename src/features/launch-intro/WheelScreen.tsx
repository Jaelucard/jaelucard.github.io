import { useLayoutEffect, useRef, type RefObject } from 'react';
import { Hero } from '../../components/Hero';
import { WHEEL_SCREEN, type IntroQuad, type WheelScreenTrack } from '../../config/intro';

const CLAMP_MAX = 1;
const clamp = (value: number, min = 0, max = CLAMP_MAX) => Math.min(max, Math.max(min, value));
const ease = (value: number) => value * value * (3 - 2 * value);
const lerp = (from: number, to: number, progress: number) => from + (to - from) * progress;

function project(width: number, height: number, quad: IntroQuad) {
  const [[x0, y0], [x1, y1], [x2, y2], [x3, y3]] = quad;
  const dx1 = x1 - x2;
  const dx2 = x3 - x2;
  const dx3 = x0 - x1 + x2 - x3;
  const dy1 = y1 - y2;
  const dy2 = y3 - y2;
  const dy3 = y0 - y1 + y2 - y3;
  const determinant = dx1 * dy2 - dx2 * dy1;

  // A homography lets the page follow all four corners of the glazed display.
  const g = (dx3 * dy2 - dx2 * dy3) / determinant;
  const h = (dx1 * dy3 - dx3 * dy1) / determinant;
  return `matrix3d(${[
    (x1 - x0 + g * x1) / width, (y1 - y0 + g * y1) / width, 0, g / width,
    (x3 - x0 + h * x3) / height, (y3 - y0 + h * y3) / height, 0, h / height,
    0, 0, 1, 0,
    x0, y0, 0, 1,
  ].join(',')})`;
}

export function WheelScreen({ track, videoRef }: {
  track: WheelScreenTrack;
  videoRef: RefObject<HTMLVideoElement | null>;
}) {
  const projectionRef = useRef<HTMLDivElement>(null);
  const previewRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const video = videoRef.current;
    const projection = projectionRef.current;
    const preview = previewRef.current;
    if (!video || !projection || !preview) return;

    const title = preview.querySelector<HTMLElement>('.poster-title');
    const poster = title?.parentElement;
    const hero = poster?.parentElement;
    let frame = 0;
    let width = 0;
    let height = 0;
    let titleCenter = 0;
    let lastTime = -1;

    function measure() {
      if (!video || !projection || !preview) return;
      width = video.clientWidth;
      height = video.clientHeight;
      projection.style.width = `${width}px`;
      preview.style.height = `${height}px`;
      titleCenter = title && poster && hero
        ? title.offsetTop + title.offsetHeight / 2 + poster.offsetTop + hero.offsetTop
        : height / 2;
      lastTime = -1;
    }

    function update() {
      if (!video || !projection || !preview) return;
      const time = video.currentTime;
      const { appearSec, zoomSec, fullSec } = WHEEL_SCREEN;
      if (width && height && time !== lastTime && time >= appearSec) {
        lastTime = time;
        const progress = clamp((time - zoomSec) / (fullSec - zoomSec));
        const camera = ease(clamp(progress / 0.84));
        const reveal = ease(clamp((progress - 0.47) / 0.53));
        const cover = Math.max(width / track.width, height / track.height);
        const offsetX = (width - track.width * cover) / 2;
        const offsetY = (height - track.height * cover) / 2;
        const [tl, tr, br, bl] = track.corners.map(([x, y]) => [x * cover + offsetX, y * cover + offsetY]);
        const centerX = (tl[0] + tr[0] + br[0] + bl[0]) / 4;
        const centerY = (tl[1] + tr[1] + br[1] + bl[1]) / 4;
        const panelWidth = (tr[0] + br[0] - tl[0] - bl[0]) / 2;
        const scale = Math.pow(Math.max(1, width * 0.96 / panelWidth), camera);
        const x = (1 - scale) * centerX + (width / 2 - centerX) * camera;
        const y = (1 - scale) * centerY + (height / 2 - centerY) * camera;
        const expand = (point: number[], toX: number, toY: number) => [
          lerp(point[0] * scale + x, toX, reveal),
          lerp(point[1] * scale + y, toY, reveal),
        ] as const;
        const quad: IntroQuad = [expand(tl, 0, 0), expand(tr, width, 0), expand(br, width, height), expand(bl, 0, height)];
        const projectedWidth = (quad[1][0] + quad[2][0] - quad[0][0] - quad[3][0]) / 2;
        const projectedHeight = (quad[2][1] + quad[3][1] - quad[0][1] - quad[1][1]) / 2;
        const cropHeight = Math.min(height, projectedHeight * width / projectedWidth);
        const cropTop = clamp(titleCenter - cropHeight / 2, 0, height - cropHeight);

        // Show a readable crop in the widescreen dash, then expand to the real viewport.
        projection.style.height = `${cropHeight}px`;
        projection.style.transform = project(width, cropHeight, quad);
        projection.style.opacity = `${ease(clamp((time - appearSec) / 0.16))}`;
        projection.style.filter = `brightness(${lerp(0.84, 1, reveal)})`;
        preview.style.transform = `translateY(${-cropTop}px)`;
        video.style.transform = `translate(${x}px, ${y}px) scale(${scale})`;
        video.style.opacity = `${lerp(1, 0.25, reveal)}`;
      }
      frame = requestAnimationFrame(update);
    }

    measure();
    frame = requestAnimationFrame(update);
    window.addEventListener('resize', measure);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('resize', measure);
      video.style.removeProperty('transform');
      video.style.removeProperty('opacity');
    };
  }, [track, videoRef]);

  return (
    <div className="launch-wheel-projection" aria-hidden="true" inert ref={projectionRef}>
      <div className="launch-wheel-preview" ref={previewRef}><Hero preview /></div>
    </div>
  );
}
