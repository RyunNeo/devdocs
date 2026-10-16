import { test, expect } from "@playwright/test";

for (const width of [1440, 390]) {
  test(`knowledge header persists across tabs at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const account = await page.request.post('/api/auth/register', { data: {
      email: `header-${Date.now()}-${width}@example.com`, password: 'Study-safe-2026!',
    } });
    expect(account.status()).toBe(201);
    const kb = await (await page.request.post('/api/knowledge-bases', { data: {
      name: '固定标题测试', description: '切换标签时保留知识库名称与描述',
    } })).json();
    let metadataRequests = 0;
    page.on('request', request => {
      if (new URL(request.url()).pathname === `/api/knowledge-bases/${kb.id}`) metadataRequests++;
    });
    await page.goto(`/knowledge-bases/${kb.id}`);
    const heading = page.getByRole('heading', { name: kb.name, exact: true });
    await expect(heading).toBeVisible();
    // Development Strict Mode may start and abort an initial request.
    const initialMetadataRequests = metadataRequests;
    const originalHeading = await heading.elementHandle();
    const originalTabs = await page.getByRole('navigation', { name: '知识库页面' }).elementHandle();
    const originalBox = await originalTabs!.boundingBox();
    for (const label of ['问答', '历史会话', '文档']) {
      await page.getByRole('link', { name: label, exact: true }).click();
      await expect(page.getByRole('link', { name: label, exact: true })).toHaveAttribute('aria-current', 'page');
      expect(await originalHeading!.evaluate(node => node.isConnected)).toBe(true);
      expect(await originalTabs!.evaluate(node => node.isConnected)).toBe(true);
      await expect(page.getByText(kb.description, { exact: true })).toBeVisible();
      expect(await originalTabs!.boundingBox()).toEqual(originalBox);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    }
    expect(metadataRequests).toBe(initialMetadataRequests);
    await expect(page.getByRole('heading', { name: '暂无文档', exact: true })).toBeVisible();
    await page.screenshot({ path: `../../work/knowledge-header-${width}.png`, fullPage: true });
  });
}

test('header survives child loading and failure, and updates for another knowledge base', async ({ page }) => {
  const account = await page.request.post('/api/auth/register', { data: {
    email: `header-errors-${Date.now()}@example.com`, password: 'Study-safe-2026!',
  } });
  expect(account.status()).toBe(201);
  const create = async (name: string, description: string) =>
    (await (await page.request.post('/api/knowledge-bases', { data: { name, description } })).json());
  const first = await create('第一份知识库', '第一份描述');
  const second = await create('第二份知识库', '第二份描述');
  await page.goto(`/knowledge-bases/${first.id}`);
  await expect(page.getByRole('heading', { name: first.name, exact: true })).toBeVisible();
  const header = await page.locator('.knowledge-base-header').elementHandle();
  const box = await header!.boundingBox();
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route(`**/api/knowledge-bases/${first.id}/conversations?limit=20*`, async route => {
    await gate;
    await route.fulfill({ status: 503, json: { detail: '会话服务暂不可用' } });
  });
  try {
    await page.getByRole('link', { name: '历史会话', exact: true }).click();
    await expect(page.getByText('正在加载会话…', { exact: true })).toBeVisible();
    expect(await header!.evaluate(node => node.isConnected)).toBe(true);
    expect(await header!.boundingBox()).toEqual(box);
    release();
    await expect(page.locator('.conversation-history').getByRole('alert')).toContainText('会话服务暂不可用');
    expect(await header!.boundingBox()).toEqual(box);
    await page.getByRole('link', { name: '文档', exact: true }).click();
    await expect(page.getByLabel('选择文档')).toBeVisible();
    await page.locator('.knowledge-base-header').getByRole('link', { name: '知识库', exact: true }).click();
    await page.getByRole('link', { name: second.name, exact: true }).click();
    await expect(page.getByRole('heading', { name: second.name, exact: true })).toBeVisible();
    await expect(page.getByText(second.description, { exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: first.name, exact: true })).toHaveCount(0);
  } finally { release(); }
});

test('returning to the window refreshes renamed metadata without replacing the header', async ({ page }) => {
  const account = await page.request.post('/api/auth/register', { data: {
    email: `header-focus-${Date.now()}@example.com`, password: 'Study-safe-2026!',
  } });
  expect(account.status()).toBe(201);
  const kb = await (await page.request.post('/api/knowledge-bases', { data: { name: '原名称' } })).json();
  await page.goto(`/knowledge-bases/${kb.id}`);
  await expect(page.getByRole('heading', { name: '原名称', exact: true })).toBeVisible();
  const header = await page.locator('.knowledge-base-header').elementHandle();
  expect((await page.request.patch(`/api/knowledge-bases/${kb.id}`, { data: {
    name: '修改后的名称', description: '来自另一个页面的修改',
  } })).status()).toBe(200);
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(page.getByRole('heading', { name: '修改后的名称', exact: true })).toBeVisible();
  await expect(page.getByText('来自另一个页面的修改', { exact: true })).toBeVisible();
  expect(await header!.evaluate(node => node.isConnected)).toBe(true);
});
