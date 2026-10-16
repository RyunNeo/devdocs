import { test, expect } from "@playwright/test";

test("knowledge chat streams, cites, follows up and survives refresh", async ({ page }) => {
  await page.goto('/register');
  await page.getByLabel('邮箱', { exact: true }).fill(`chat-${Date.now()}@example.com`);
  await page.getByLabel('密码', { exact: true }).fill('Study-safe-2026!');
  await page.getByLabel('确认密码').fill('Study-safe-2026!');
  await page.getByRole('button', { name: '创建账号' }).click();
  await expect(page).toHaveURL(/dashboard$/);
  const kb = await (await page.request.post('/api/knowledge-bases', { data: { name: 'React 问答' } })).json();
  const doc = await (await page.request.post(`/api/knowledge-bases/${kb.id}/documents`, { multipart: {
    file: { name: 'react.md', mimeType: 'text/markdown', buffer: Buffer.from('# React\n\n组件使用状态。') },
  } })).json();
  expect((await page.request.post(`/api/documents/${doc.id}/index`)).status()).toBe(200);
  await page.goto(`/knowledge-bases/${kb.id}/chat`);
  await expect(page.getByRole('heading', { name: 'React 问答' })).toBeVisible();
  await page.getByLabel('问题', { exact: true }).fill('组件如何使用状态？');
  await page.getByRole('button', { name: '发送问题', exact: true }).click();
  await expect(page.getByText('回答完成', { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/conversation=/);
  await page.getByRole('button', { name: '查看引用 1', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '引用原文' });
  await expect(dialog).toContainText('react.md');
  await expect(dialog).toContainText('组件使用状态');
  await page.keyboard.press('Escape');
  await page.getByLabel('问题', { exact: true }).fill('再说明一下');
  await page.getByRole('button', { name: '发送问题', exact: true }).click();
  await expect(page.getByText('回答完成', { exact: true })).toHaveCount(2);
  await page.reload();
  await expect(page.getByText('回答完成', { exact: true })).toHaveCount(2);
  await page.getByLabel('问题', { exact: true }).fill('慢一点说明');
  await page.getByRole('button', { name: '发送问题', exact: true }).click();
  await expect(page.getByText('正在生成', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '停止生成', exact: true }).click();
  await expect(page.getByText('已停止', { exact: true })).toBeVisible();
  await page.waitForTimeout(500);
  await page.reload();
  await expect(page.getByText('已停止', { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  const lastMessage=await page.locator('.chat-message').last().boundingBox();
  const composer=await page.locator('.chat-composer').boundingBox();
  expect(composer!.y).toBeGreaterThanOrEqual(lastMessage!.y+lastMessage!.height);
  await page.screenshot({ path: '../../work/chat-mobile.png', fullPage: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({ path: '../../work/chat-desktop.png', fullPage: true });
});

test('new conversation recovers from an inaccessible conversation', async ({ page }) => {
  await page.request.post('/api/auth/register', { data: { email: `recover-${Date.now()}@example.com`, password:'Study-safe-2026!' } });
  const kb=await (await page.request.post('/api/knowledge-bases',{data:{name:'恢复会话'}})).json();
  await page.goto(`/knowledge-bases/${kb.id}/chat?conversation=00000000-0000-0000-0000-000000000001`);
  await expect(page.getByRole('alert').filter({hasText:'会话不存在'})).toBeVisible();
  await page.getByRole('button',{name:'新会话',exact:true}).click();
  await page.getByLabel('问题',{exact:true}).fill('问题');
  await expect(page.getByRole('button',{name:'发送问题',exact:true})).toBeEnabled();
});
