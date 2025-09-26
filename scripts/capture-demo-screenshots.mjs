// Capture preview UI screenshots (preview screen, edit dialog, approve toast)
// Requires: `npx playwright install chromium`
import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';

const BASE_URL = process.env.PREVIEW_URL || 'http://127.0.0.1:8787/ui';
const OUT_DIR = path.resolve('docs/temp');

async function ensureOutDir() {
  await fs.mkdir(OUT_DIR, { recursive: true });
}

async function run() {
  await ensureOutDir();
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();

  await page.goto(BASE_URL, { waitUntil: 'networkidle' });
  await page.waitForSelector('text=Review & Approve', { timeout: 5000 });

  await page.screenshot({ path: path.join(OUT_DIR, 'demo-preview.png') });

  // Open Edit dialog and submit a note
  await page.getByRole('button', { name: /edit/i }).click();
  await page.getByPlaceholder(/Add quick edit notes/i).fill('Demo edit for screenshot');
  await page.getByRole('button', { name: /submit edit/i }).click();
  await page.waitForSelector('text=Edit captured', { timeout: 5000 });
  await page.screenshot({ path: path.join(OUT_DIR, 'demo-preview-edit.png') });

  // Approve and capture toast
  await page.getByRole('button', { name: /approve/i }).click();
  await page.waitForSelector('text=Preview approved', { timeout: 5000 });
  await page.screenshot({ path: path.join(OUT_DIR, 'demo-preview-approved.png') });

  await browser.close();
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});

