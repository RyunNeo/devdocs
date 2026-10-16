import { test, expect, type Page } from '@playwright/test';

async function prepare(page: Page) {
  expect((await page.request.post('/api/auth/register', { data: {
    email: `typing-${Date.now()}-${Math.random()}@example.com`, password: 'Study-safe-2026!',
  } })).status()).toBe(201);
  const kb = await (await page.request.post('/api/knowledge-bases', { data: { name: '逐步展示' } })).json();
  const doc = await (await page.request.post(`/api/knowledge-bases/${kb.id}/documents`, { multipart: {
    file: { name: 'react.md', mimeType: 'text/markdown', buffer: Buffer.from('# React\n组件使用状态。') },
  } })).json();
  expect((await page.request.post(`/api/documents/${doc.id}/index`)).status()).toBe(200);
  await page.goto(`/knowledge-bases/${kb.id}/chat?new=1`);
  await expect(page.getByLabel('问题', { exact: true })).toBeVisible();
  return kb.id;
}

test('waiting animates, validated answer types progressively, skip shows citations and history does not replay', async ({ page }) => {
  const kb = await prepare(page);
  await page.getByLabel('问题', { exact: true }).fill('慢一点解释');
  await page.getByLabel('问题', { exact: true }).press('Enter');
  await expect(page.locator('.chat-processing-dots')).toBeVisible();
  expect(await page.locator('.chat-processing-dots i').first().evaluate(node => getComputedStyle(node).animationName)).not.toBe('none');
  const assistant = page.locator('.chat-message.assistant').last();
  await expect(assistant.locator('.chat-body')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '立即显示全部', exact: true })).toBeVisible({ timeout: 15000 });
  const full = '组件使用状态，保持数据更新。 [1]';
  expect((await assistant.locator('.chat-body').innerText()).length).toBeLessThan(full.length);
  await expect(assistant.locator('.chat-citations')).toHaveCount(0);
  await page.getByRole('button', { name: '立即显示全部', exact: true }).focus();
  await page.getByRole('button', { name: '立即显示全部', exact: true }).press('Enter');
  await expect(assistant.locator('.chat-body')).toBeFocused();
  await expect(assistant.locator('.chat-body')).toHaveText(full);
  await expect(page.getByRole('button', { name: '查看引用 1', exact: true })).toBeVisible();
  await page.getByRole('link', { name: '历史会话', exact: true }).click();
  await page.getByRole('link', { name: '慢一点解释', exact: true }).click();
  await expect(page.locator('.chat-body').last()).toHaveText(full);
  await expect(page.getByRole('button', { name: '立即显示全部', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '新会话', exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`${kb}/chat\\?new=1`));
  await expect(page.locator('.chat-message')).toHaveCount(0);
});

test('typing completes naturally on mobile and reduced motion shows full answers immediately', async ({ page }) => {
  await prepare(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByLabel('问题', { exact: true }).fill('解释状态');
  await page.getByLabel('问题', { exact: true }).press('Enter');
  await expect(page.getByRole('button', { name: '立即显示全部', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '立即显示全部', exact: true }).focus();
  await page.screenshot({ path: '../../work/typewriter-mobile.png', fullPage: true });
  await expect(page.getByText('回答完成', { exact: true })).toBeVisible();
  await expect(page.locator('.chat-message.assistant .chat-body').last()).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.getByLabel('问题', { exact: true }).fill('再解释');
  await page.getByLabel('问题', { exact: true }).press('Enter');
  await expect(page.getByText('回答完成', { exact: true })).toHaveCount(2);
  await expect(page.getByRole('button', { name: '立即显示全部', exact: true })).toHaveCount(0);
});

test('long Unicode answers accelerate, preserve graphemes and clear on new conversation', async ({ page }) => {
  await prepare(page);
  const answer = '状态👩🏽‍💻e\u0301\n'.repeat(600);
  let streams = 0;
  await page.route('**/api/conversations/*/chat/stream', async route => {
    streams++;
    const { request_id } = route.request().postDataJSON();
    const conversation = route.request().url().split('/conversations/')[1].split('/')[0];
    const frame = (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
    await route.fulfill({ contentType: 'text/event-stream', body:
      frame('meta', { conversation_id: conversation, run_id: request_id, assistant_message_id: 'animated-answer', user_sequence: 1 }) +
      frame('token', { delta: answer }) +
      frame('done', { message_id: 'animated-answer', status: 'completed', content: answer, usage: null }),
    });
  });
  await page.getByLabel('问题', { exact: true }).fill('完整展示长答案');
  await page.getByLabel('问题', { exact: true }).press('Enter');
  await expect(page.getByRole('button', { name: '立即显示全部', exact: true })).toBeVisible();
  const body = page.locator('.chat-message.assistant .chat-body');
  const partial = await body.textContent() ?? '';
  expect(partial.length).toBeLessThan(answer.length);
  const boundaries = new Set([0]);
  let boundary = 0;
  for (const unit of new Intl.Segmenter('zh', { granularity: 'grapheme' }).segment(answer)) {
    boundary += unit.segment.length; boundaries.add(boundary);
  }
  expect(boundaries.has(partial.length)).toBe(true);
  await expect.poll(async () => (await body.textContent())?.length).toBeGreaterThan(partial.length);
  await expect(page.getByText('回答完成', { exact: true })).toBeVisible({ timeout: 6500 });
  expect(await body.textContent()).toBe(answer);
  expect(streams).toBe(1);
  await page.getByRole('button', { name: '新会话', exact: true }).click();
  await page.getByLabel('问题', { exact: true }).fill('展示时切换');
  await page.getByLabel('问题', { exact: true }).press('Enter');
  await expect(page.getByRole('button', { name: '立即显示全部', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '新会话', exact: true }).click();
  await expect(page.getByText('暂无消息', { exact: true })).toBeVisible();
  await expect(page.locator('.chat-typing')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '立即显示全部', exact: true })).toHaveCount(0);
});
