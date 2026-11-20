import { expect, test } from '@playwright/test';

test.use({ reducedMotion: 'no-preference' });

const intro = (page) => page.getByRole('region', { name: 'F1 cockpit launch animation' });

test('first visit hands off to the Hero and reload skips the curtain', async ({ page }) => {
  await page.goto('/');
  await expect(intro(page)).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-intro', 'active');
  await expect(intro(page)).toHaveCount(0, { timeout: 8_000 });
  await expect(page.getByRole('heading', { name: 'JARROD' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Primary' })).toBeVisible();
  await expect(page.locator('html')).not.toHaveAttribute('data-intro', /.+/);
  expect(await page.evaluate(() => localStorage.getItem('jarrod_f1_intro_seen_v1'))).toBe('true');
  await page.reload();
  await expect(page.locator('html')).not.toHaveAttribute('data-intro', /.+/);
  await expect(intro(page)).toHaveCount(0);
});

test('forced replay, Escape, and the footer replay preserve keyboard access', async ({ page }) => {
  await page.goto('/?intro=1');
  await expect(intro(page)).toBeVisible();
  await page.keyboard.press('Tab');
  await expect(intro(page).getByRole('button', { name: 'Skip intro' })).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('main')).toBeFocused();
  await expect(intro(page)).toHaveCount(0);

  await page.getByRole('button', { name: 'Replay intro' }).click();
  await expect(intro(page)).toBeVisible();
  await intro(page).getByRole('button', { name: 'Skip intro' }).click();
  await expect(intro(page)).toHaveCount(0);
  await expect(page.getByRole('main')).toBeFocused();
});

test('capture framing and reduced motion bypass playback', async ({ page }) => {
  await page.goto('/?capture=hero&intro=1');
  await expect(page.locator('html')).toHaveAttribute('data-capture', 'hero');
  await expect(page.getByRole('heading', { name: 'JARROD' })).toBeVisible();
  await expect(page.locator('#nav')).toBeHidden();
  await expect(page.locator('.hero-scroll')).toBeHidden();
  await expect(intro(page)).toHaveCount(0);

  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/?intro=1');
  await expect(page.getByRole('navigation', { name: 'Primary' })).toBeVisible();
  await expect(page.locator('html')).not.toHaveAttribute('data-intro', /.+/);
  await expect(intro(page)).toHaveCount(0);
});
