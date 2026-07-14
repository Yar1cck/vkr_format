import { test, expect } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const API = (p: string) =>
  `${process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost'}/api/v1${p}`;

const FIXTURE = path.resolve(__dirname, '..', '..', 'tests', 'fixtures', 'all_violations.docx');

function uniqueEmail(): string {
  return `pw-up-${Math.random().toString(36).slice(2, 10)}@example.com`;
}

async function registerAndLogin(page, request) {
  const email = uniqueEmail();
  const password = 'Passw0rd!Strong';
  const reg = await request.post(API('/auth/register'), {
    data: { email, full_name: 'PW Student', password },
  });
  if (reg.status() === 429) {
    test.skip(true, 'rate-limit на /register');
  }
  expect(reg.ok()).toBeTruthy();
  const lg = await request.post(API('/auth/login'), { data: { email, password } });
  expect(lg.ok()).toBeTruthy();
  const tokens = await lg.json();

  // Кладём токены в sessionStorage (как и делает useAuthStore)
  await page.goto('/');
  await page.evaluate((t) => {
    sessionStorage.setItem('access_token', t.access_token);
    sessionStorage.setItem('refresh_token', t.refresh_token);
  }, tokens);
  await page.reload();
  return { email, tokens };
}

test('студент видит страницу после входа', async ({ page, request }) => {
  await registerAndLogin(page, request);
  // После входа AuthPage пропадает — заголовок «ВКР.Формат» с подзаголовком уже не видим
  await expect(page.getByText(/Оформление выпускной квалификационной/i)).toBeHidden({ timeout: 5_000 });
});

test('загрузка .docx обрабатывается и появляются нарушения', async ({ page, request }) => {
  await registerAndLogin(page, request);

  // input[type=file] невидим (sr-only), но Playwright умеет с ним работать
  const input = page.locator('input[type="file"]').first();
  await input.setInputFiles(FIXTURE);

  // Документ должен появиться в списке. Стек обрабатывает быстро (~10s).
  // Ждём, пока статус сменится с pending/processing на done.
  await expect(page.locator('text=/processing|обработка|загруж/i').first())
    .toBeVisible({ timeout: 30_000 });

  await expect.poll(async () => {
    const r = await request.get(API('/documents/'), {
      headers: {
        Authorization: `Bearer ${await page.evaluate(() => sessionStorage.getItem('access_token'))}`,
      },
    });
    const docs = await r.json();
    return docs[0]?.status;
  }, { timeout: 60_000, intervals: [2_000] }).toBe('done');

  // На странице должно быть какое-то упоминание нарушений
  // (карточки нарушений или счётчик)
  await page.reload();
  await expect(page.locator('text=/нарушени|замечани/i').first())
    .toBeVisible({ timeout: 10_000 });
});
