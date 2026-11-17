import { test, expect } from '@playwright/test';

const errors = new WeakMap();
test.beforeEach(({ page }) => {
  const messages = [];
  errors.set(page, messages);
  page.on('pageerror', (error) => messages.push(error.message));
});
test.afterEach(async ({ page }, testInfo) => {
  const messages = errors.get(page) ?? [];
  if (messages.length) await testInfo.attach('uncaught-browser-errors', {
    body: JSON.stringify(messages, null, 2), contentType: 'application/json',
  });
  expect.soft(messages, 'No uncaught browser exceptions').toEqual([]);
});

async function openGame(page, url = '/#marina-bay') {
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  const section = page.locator('#marina-bay');
  await section.getByRole('button', { name: /Start your lap/ }).click();
  const canvas = section.locator('canvas');
  await expect(canvas).toBeVisible();
  await canvas.scrollIntoViewIfNeeded();
  await expect(canvas).toBeInViewport({ ratio: 0.5 });
  const resume = section.getByRole('button', { name: 'Resume lap', exact: true });
  if (await resume.isVisible()) await resume.click();
  await canvas.focus();
  return { section, canvas, status: section.locator('.mb-session-status'), timer: section.locator('.mb-timer') };
}

async function capture(page, testInfo, name) {
  const path = testInfo.outputPath(`${name}.png`);
  if (page.viewportSize().width < 700) await page.screenshot({ path, animations: 'disabled' });
  else await page.locator('#marina-bay .mb-shell').screenshot({ path, animations: 'disabled' });
  await testInfo.attach(name, { path, contentType: 'image/png' });
}

const speed = (page) => page.locator('#marina-bay .mb-speed-line strong');
const heldButton = (page, action) => page.locator(`#marina-bay .mb-touch-button[data-action="${action}"]`);
const displayedSpeed = async (page) => Number(await speed(page).textContent());

test('production: keyboard controls, arrow scrolling, pause, reset and focus boundaries', async ({ page }, testInfo) => {
  const { section, canvas, status, timer } = await openGame(page);
  expect(await page.evaluate(() => typeof window.__MARINA_BAY_GAME__)).toBe('undefined');
  await expect(canvas).toBeFocused();
  const initialScroll = await page.evaluate(() => window.scrollY);
  await page.keyboard.down('ArrowUp');
  await expect.poll(() => displayedSpeed(page)).toBeGreaterThan(20);
  await expect(heldButton(page, 'throttle')).toHaveAttribute('data-held', 'true');
  await page.keyboard.down('d');
  await expect(heldButton(page, 'right')).toHaveAttribute('data-held', 'true');
  await page.waitForTimeout(180); // A real held steering input, not a simulated state mutation.
  await page.keyboard.up('d');
  await page.keyboard.up('ArrowUp');
  expect(await page.evaluate(() => window.scrollY)).toBe(initialScroll);
  await expect(timer).not.toHaveText('00:00.000');
  await capture(page, testInfo, 'desktop-1440-active');

  await section.locator('.mb-actions').getByRole('button', { name: /^Pause/ }).click();
  await expect(status).toHaveAttribute('data-paused', 'true');
  const pausedTime = await timer.textContent();
  await page.waitForTimeout(350); // Verify that elapsed time stays frozen across several HUD intervals.
  await expect(timer).toHaveText(pausedTime);
  await expect(heldButton(page, 'throttle')).toHaveAttribute('data-held', 'false');
  await capture(page, testInfo, 'desktop-1440-paused');
  await section.getByRole('button', { name: 'Resume lap', exact: true }).click();
  await expect(canvas).toBeFocused();
  await page.keyboard.press('r');
  await expect(timer).toHaveText('00:00.000');
  await expect(speed(page)).toHaveText('0');
  await expect(section.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0');

  await page.locator('a').first().focus();
  await expect(status).toHaveAttribute('data-paused', 'true');
  const outsideScroll = await page.evaluate(() => window.scrollY);
  await page.keyboard.press('ArrowDown');
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(outsideScroll);
  await expect(timer).toHaveText('00:00.000');
  await expect(speed(page)).toHaveText('0');
});

test('production: an offscreen canvas pauses while the rest of the widget remains visible', async ({ page }) => {
  const { canvas, section, status, timer } = await openGame(page);
  await page.keyboard.down('w');
  await expect.poll(() => displayedSpeed(page)).toBeGreaterThan(15);
  await page.keyboard.up('w');
  const box = await canvas.boundingBox();
  expect(box).not.toBeNull();
  await page.evaluate((bottom) => window.scrollTo({ top: window.scrollY + bottom + 5, behavior: 'instant' }), box.y + box.height);
  await expect(canvas).not.toBeInViewport();
  await expect(section.getByRole('group', { name: 'Marina Bay driving game', exact: true })).toBeInViewport();
  await expect(status).toHaveAttribute('data-paused', 'true');
  const stopped = await timer.textContent();
  await page.waitForTimeout(250);
  await expect(timer).toHaveText(stopped);
  await expect(heldButton(page, 'throttle')).toHaveAttribute('data-held', 'false');
});

for (const width of [390, 320]) {
  test.describe(`production touch at ${width}px`, () => {
    test.use({ viewport: { width, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 1 });
    test('simultaneous pedals and steering, cancellation, and overflow', async ({ page, context }, testInfo) => {
      const { canvas } = await openGame(page);
      await canvas.scrollIntoViewIfNeeded();
      const accelerator = heldButton(page, 'throttle');
      const steering = heldButton(page, 'right');
      await expect(accelerator).toBeInViewport();
      await expect(steering).toBeInViewport();
      const canvasBounds = await canvas.boundingBox();
      const navigationBounds = await page.locator('#nav').boundingBox();
      expect(canvasBounds.y, 'Fixed navigation must not cover the circuit').toBeGreaterThanOrEqual(navigationBounds.y + navigationBounds.height);
      expect(canvasBounds.y + canvasBounds.height, 'Full circuit is visible').toBeLessThanOrEqual(844);
      const centre = async (locator, id) => {
        const box = await locator.boundingBox();
        expect(box).not.toBeNull();
        return { id, x: box.x + box.width / 2, y: box.y + box.height / 2, radiusX: 4, radiusY: 4, force: 1 };
      };
      const throttlePoint = await centre(accelerator, 1);
      const steeringPoint = await centre(steering, 2);
      const scrollBefore = await page.evaluate(() => window.scrollY);
      const cdp = await context.newCDPSession(page);
      try {
        // CDP creates real browser touch/pointer events and pointer capture.
        await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [throttlePoint] });
        await expect.poll(() => displayedSpeed(page)).toBeGreaterThan(15);
        await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [throttlePoint, steeringPoint] });
        await expect(accelerator).toHaveAttribute('data-held', 'true');
        await expect(steering).toHaveAttribute('data-held', 'true');
        await page.waitForTimeout(180);
        expect(await page.evaluate(() => window.scrollY)).toBe(scrollBefore);
        await cdp.send('Input.dispatchTouchEvent', { type: 'touchCancel', touchPoints: [] });
        await expect(accelerator).toHaveAttribute('data-held', 'false');
        await expect(steering).toHaveAttribute('data-held', 'false');
        await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [throttlePoint] });
        await expect(accelerator).toHaveAttribute('data-held', 'true');
        await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
        await expect(accelerator).toHaveAttribute('data-held', 'false');
      } finally {
        await cdp.send('Input.dispatchTouchEvent', { type: 'touchCancel', touchPoints: [] }).catch(() => {});
        await cdp.detach();
      }
      const layout = await page.evaluate(() => ({ width: innerWidth, page: document.documentElement.scrollWidth,
        game: document.querySelector('#marina-bay .mb-shell').getBoundingClientRect().toJSON() }));
      expect(layout.page, 'Page should not scroll horizontally').toBeLessThanOrEqual(layout.width + 1);
      expect(layout.game.x).toBeGreaterThanOrEqual(0);
      expect(layout.game.right).toBeLessThanOrEqual(layout.width + 1);
      await capture(page, testInfo, `mobile-${width}-active`);
    });
  });
}

test('development: an automated driver completes the entire circuit and the best survives reload', async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  const { section } = await openGame(page, 'http://127.0.0.1:5173/#marina-bay');
  await expect.poll(() => page.evaluate(() => typeof window.__MARINA_BAY_GAME__)).toBe('object');
  const result = await page.evaluate(async () => {
    const { sampleTrack, projectToTrack } = await import('/src/features/marina-bay/track.ts');
    const driver = window.__MARINA_BAY_GAME__;
    const angle = (value) => Math.atan2(Math.sin(value), Math.cos(value));
    const checkpoints = new Set([0]);
    const route = [];
    let offTrackFrames = 0;
    // Only setInput and advance affect the car. There are no teleports or writes
    // to its position, speed, heading, checkpoint progress or lap results.
    for (let frame = 0; frame < 180 * 120 && driver.snapshot().lastResultId === 0; frame++) {
      const state = driver.snapshot();
      const position = projectToTrack(state.x, state.y);
      const target = sampleTrack(position.s + Math.max(12, Math.abs(state.speed) * 0.45));
      const turn = angle(Math.atan2(target.y - state.y, target.x - state.x) - state.heading);
      const curvature = Math.abs(angle(sampleTrack(position.s + 35).angle - position.angle));
      const targetSpeed = curvature > 0.6 ? 20 : curvature > 0.25 ? 35 : 62;
      driver.setInput({ throttle: state.speed < targetSpeed, brake: state.speed > targetSpeed + 2,
        left: turn < -0.025, right: turn > 0.025 });
      driver.advance(1 / 120);
      const current = driver.snapshot();
      checkpoints.add(current.checkpointIndex);
      if (current.offTrack) offTrackFrames++;
      if (frame % 120 === 0) route.push({ seconds: frame / 120, x: current.x, y: current.y });
    }
    driver.setInput({});
    return { state: driver.snapshot(), checkpoints: [...checkpoints], offTrackFrames, route };
  });
  await testInfo.attach('automated-full-lap', { body: JSON.stringify(result, null, 2), contentType: 'application/json' });
  expect(result.state.lastLapValid).toBe(true);
  expect(result.state.laps).toBe(1);
  expect(result.state.lastLap).toBeGreaterThan(90);
  expect(result.state.lastLap).toBeLessThan(150);
  expect(result.checkpoints).toHaveLength(64);
  expect(result.offTrackFrames).toBe(0);
  expect(result.state.bestLap).toBe(result.state.lastLap);
  const best = section.locator('.mb-lap-records > div').first().locator('dd');
  await expect(best).not.toHaveText('--:--.---');
  const bestText = await best.textContent();
  await section.getByRole('button', { name: 'Resume lap', exact: true }).click();
  await capture(page, testInfo, 'automated-complete-lap');
  await page.reload({ waitUntil: 'domcontentloaded' });
  await section.getByRole('button', { name: /Start your lap/ }).click();
  await expect(page.locator('#marina-bay .mb-lap-records > div').first().locator('dd')).toHaveText(bestText);
});
