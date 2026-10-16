import { test, expect } from '@playwright/test';

test('usage page shows own quotas, local history, filters and mobile layout', async ({ page }) => {
  expect((await page.request.post('/api/auth/register', { data: {
    email: `usage-${Date.now()}@example.com`, password: 'Study-safe-2026!',
  } })).status()).toBe(201);
  await page.goto('/dashboard');
  await page.getByRole('link', { name: '用量', exact: true }).click();
  await expect(page.getByRole('heading', { name: '个人用量', exact: true })).toBeVisible();
  await expect(page.getByText('暂无调用记录', { exact: true })).toBeVisible();
  const kb = await (await page.request.post('/api/knowledge-bases', { data: { name: 'Usage' } })).json();
  const conv = await (await page.request.post(`/api/knowledge-bases/${kb.id}/conversations`, { data: {} })).json();
  const answer = await page.request.post(`/api/conversations/${conv.id}/chat/stream`, { data: { question: 'private sentinel question', request_id: crypto.randomUUID() } });
  expect(answer.status()).toBe(200);
  await page.getByRole('button', { name: '刷新用量', exact: true }).click();
  await expect(page.getByRole('row').filter({ hasText: '本地完成' })).toBeVisible();
  await expect(page.getByTestId('chat-quota')).toContainText('49');
  await expect(page.getByText('private sentinel question')).toHaveCount(0);
  await page.getByLabel('任务类型', { exact: true }).selectOption('index');
  await expect(page.getByText('暂无调用记录', { exact: true })).toBeVisible();
  await page.getByLabel('任务类型', { exact: true }).selectOption('');
  await expect(page.getByRole('row').filter({ hasText: '本地完成' })).toBeVisible();
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await page.screenshot({ path: `../../work/usage-${width}.png`, fullPage: true });
  }
});

test('usage separates known chat tokens from unknown query embedding usage', async ({ page }) => {
  await page.request.post('/api/auth/register', { data: { email: `usage-tokens-${Date.now()}@example.com`, password: 'Study-safe-2026!' } });
  const kb = await (await page.request.post('/api/knowledge-bases', { data: { name: 'Tokens' } })).json();
  const doc = await (await page.request.post(`/api/knowledge-bases/${kb.id}/documents`, { multipart: { file: {
    name: 'react.md', mimeType: 'text/markdown', buffer: Buffer.from('# React\n组件状态'),
  } } })).json();
  expect((await page.request.post(`/api/documents/${doc.id}/index`)).status()).toBe(200);
  const conv = await (await page.request.post(`/api/knowledge-bases/${kb.id}/conversations`, { data: {} })).json();
  await page.request.post(`/api/conversations/${conv.id}/chat/stream`, { data: { question: '组件状态', request_id: crypto.randomUUID() } });
  await page.goto('/settings/usage');
  await expect(page.getByRole('cell', { name: '30（不完整）', exact: true })).toBeVisible();
  await expect(page.getByText('1 个任务用量不完整', { exact: true })).toBeVisible();
  await page.getByLabel('任务结果', { exact: true }).selectOption('failed');
  await expect(page.getByText('暂无调用记录', { exact: true })).toBeVisible();
});

test('quota rejection preserves the unsent question and creates no answer', async ({ page }) => {
  await page.request.post('/api/auth/register', { data: { email: `usage-limit-${Date.now()}@example.com`, password: 'Study-safe-2026!' } });
  const kb = await (await page.request.post('/api/knowledge-bases', { data: { name: 'Limit' } })).json();
  await page.goto(`/knowledge-bases/${kb.id}/chat?new=1`);
  const input = page.getByLabel('问题', { exact: true });
  await input.fill('保留这个未提交的问题');
  await page.route('**/api/conversations/*/chat/stream', route => route.fulfill({ status: 429, json: {
    detail: '今日问答次数已用完，将于 10-16 00:00（UTC+08:00）重置', code: 'daily_quota_exceeded', reset_at: '2026-10-15T16:00:00Z',
  } }));
  await input.press('Enter');
  await expect(page.getByRole('alert').filter({ hasText: '今日问答次数已用完' })).toBeVisible();
  await expect(input).toHaveValue('保留这个未提交的问题');
  await expect(page.locator('.chat-message')).toHaveCount(0);
});

test('usage failure retries and a late filter response cannot replace the current selection', async ({ page }) => {
  await page.request.post('/api/auth/register', { data: { email: `usage-race-${Date.now()}@example.com`, password: 'Study-safe-2026!' } });
  let failSummary = true;
  await page.route('**/api/usage/summary', async route => {
    if (failSummary) await route.fulfill({ status: 503, json: { detail: '用量暂不可用' } });
    else await route.continue();
  });
  await page.goto('/settings/usage');
  await expect(page.getByRole('alert').filter({ hasText: '用量暂不可用' })).toBeVisible();
  failSummary = false;
  await page.getByRole('button', { name: '重试', exact: true }).click();
  await expect(page.getByText('暂无调用记录', { exact: true })).toBeVisible();
  let release!: () => void;
  let finished!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  const released = new Promise<void>(resolve => { finished = resolve; });
  await page.route('**/api/usage/events?*', async route => {
    if (!route.request().url().includes('operation=index')) return route.continue();
    await gate;
    await route.fulfill({ json: { items: [{ id: 'stale', request_id: 'stale-index-response', operation: 'index',
      status: 'failed', quota_charged: true, started_at: new Date().toISOString(), finished_at: new Date().toISOString(),
      durations_ms: { total: 1 }, models: {}, attempts: {}, token_usage: {}, error_code: 'stale-filter',
    }], total: 1, limit: 20, offset: 0 } }).catch(() => {});
    finished();
  });
  try {
    const request = page.waitForRequest(request => request.url().includes('operation=index'));
    await page.getByLabel('任务类型', { exact: true }).selectOption('index');
    await request;
    await page.getByLabel('任务类型', { exact: true }).selectOption('chat');
    await expect(page.getByText('暂无调用记录', { exact: true })).toBeVisible();
    release(); await released;
    await expect(page.getByLabel('任务类型', { exact: true })).toHaveValue('chat');
    await expect(page.getByText('stale-index-response', { exact: true })).toHaveCount(0);
  } finally { release(); }
});
