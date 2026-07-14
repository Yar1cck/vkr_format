import { test, expect } from '@playwright/test';

const API = (path: string) => `${process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost'}/api/v1${path}`;

function uniqueEmail(): string {
  return `pw-${Math.random().toString(36).slice(2, 10)}@example.com`;
}

test.describe('Auth', () => {
  test('форма входа отображается', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByPlaceholder('Email')).toBeVisible();
    await expect(page.getByPlaceholder('Пароль')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Войти' })).toBeVisible();
  });

  test('переключение между login и register', async ({ page }) => {
    await page.goto('/');
    await page.getByText('Нет аккаунта? Регистрация').click();
    await expect(page.getByPlaceholder('ФИО')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Создать аккаунт' })).toBeVisible();
    await page.getByText('Уже есть аккаунт? Вход').click();
    await expect(page.getByPlaceholder('ФИО')).toBeHidden();
  });

  test('регистрация и вход студента', async ({ page, request }) => {
    const email = uniqueEmail();
    const password = 'Passw0rd!Strong';

    // Регистрируем через API напрямую (rate-limit на /register: 5/мин — экономим).
    const reg = await request.post(API('/auth/register'), {
      data: { email, full_name: 'PW Тестовый Студент', password },
    });
    if (reg.status() === 429) test.skip(true, 'rate-limit на /register');
    expect(reg.ok()).toBeTruthy();

    await page.goto('/');
    await page.getByPlaceholder('Email').fill(email);
    await page.getByPlaceholder('Пароль').fill(password);
    await page.getByRole('button', { name: 'Войти' }).click();

    // После логина AuthPage скрывается — форма больше не видна
    await expect(page.getByPlaceholder('Email')).toBeHidden({ timeout: 10_000 });
  });

  test('неверный пароль показывает ошибку', async ({ page, request }) => {
    const email = uniqueEmail();
    const password = 'Passw0rd!Strong';
    const reg = await request.post(API('/auth/register'), {
      data: { email, full_name: 'PW Wrong', password },
    });
    if (reg.status() === 429) test.skip(true, 'rate-limit на /register');

    await page.goto('/');
    await page.getByPlaceholder('Email').fill(email);
    await page.getByPlaceholder('Пароль').fill('wrong-password-1!');
    await page.getByRole('button', { name: 'Войти' }).click();

    // Сообщение об ошибке отображается в красном div'е (bg-red-50/text-red-700).
    await expect(page.locator('div.bg-red-50, [class*="text-red"]').first()).toBeVisible({ timeout: 5_000 });
  });
});
