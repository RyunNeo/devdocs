import { test, expect, type Page } from '@playwright/test';
import type { DocumentRecord } from '@/lib/documents';

async function prepare(page: Page) {
  expect((await page.request.post('/api/auth/register', { data: {
    email: `batch-${Date.now()}-${Math.random()}@example.com`, password: 'Study-safe-2026!',
  } })).status()).toBe(201);
  const kb = await (await page.request.post('/api/knowledge-bases', { data: { name: '批量文档' } })).json();
  await page.goto(`/knowledge-bases/${kb.id}`);
  await expect(page.getByLabel('选择文档', { exact: true })).toBeVisible();
  return kb.id as string;
}
const file = (name: string, content = name) => ({ name, mimeType: 'text/plain', buffer: Buffer.from(content) });

test('multiple uploads, page selection, batch indexing and confirmed deletion clean up chunks', async ({ page }) => {
  const kb = await prepare(page);
  await page.getByLabel('选择文档', { exact: true }).setInputFiles([file('first.md'), file('second.txt')]);
  await page.getByRole('button', { name: '上传文档', exact: true }).click();
  await expect(page.getByText('2 个文档', { exact: true })).toBeVisible();
  await expect(page.getByLabel('选择文档', { exact: true })).toBeFocused();
  await page.getByRole('checkbox', { name: '全选当前页', exact: true }).check();
  await expect(page.getByText('已选择 2 个文档', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '批量建立索引', exact: true }).click();
  const indexing = page.getByRole('dialog', { name: '批量建立索引', exact: true });
  await expect(indexing).toContainText('可能产生费用');
  await indexing.getByRole('button', { name: '确认建立索引', exact: true }).click();
  await expect(indexing.getByText('成功 2', { exact: true })).toBeVisible();
  await indexing.getByRole('button', { name: '关闭', exact: true }).click();
  const docs = (await (await page.request.get(`/api/knowledge-bases/${kb}/documents`)).json()).items;
  for (const doc of docs) expect((await (await page.request.get(`/api/documents/${doc.id}/chunks`)).json()).total).toBeGreaterThan(0);
  await page.getByRole('checkbox', { name: '全选当前页', exact: true }).check();
  await page.getByRole('button', { name: '批量删除', exact: true }).click();
  const deletion = page.getByRole('dialog', { name: '批量删除文档', exact: true });
  await deletion.getByRole('button', { name: '取消', exact: true }).click();
  await expect(page.getByText('2 个文档', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '批量删除', exact: true }).click();
  await deletion.getByRole('button', { name: '确认删除', exact: true }).click();
  await expect(deletion.getByText('成功 2', { exact: true })).toBeVisible();
  await deletion.getByRole('button', { name: '关闭', exact: true }).click();
  await expect(page.getByText('0 个文档', { exact: true })).toBeVisible();
  for (const doc of docs) expect((await page.request.get(`/api/documents/${doc.id}/chunks`)).status()).toBe(404);
});

test('invalid files and duplicate failures do not discard other successful uploads', async ({ page }) => {
  await prepare(page);
  await page.getByLabel('选择文档', { exact: true }).setInputFiles([
    file('valid.md', 'same-content'), file('duplicate.txt', 'same-content'), file('unsupported.json'), file('another.txt'),
  ]);
  await page.getByRole('button', { name: '上传文档', exact: true }).click();
  const results = page.getByRole('region', { name: '上传结果', exact: true });
  await expect(results.getByText('成功 2', { exact: true })).toBeVisible();
  await expect(results.getByText('失败 1', { exact: true })).toBeVisible();
  await expect(results.getByText('已跳过 1', { exact: true })).toBeVisible();
  await expect(results).toContainText('已有相同内容');
  await expect(page.getByText('2 个文档', { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('checkbox', { name: '全选当前页', exact: true }).check();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: '../../work/batch-documents-mobile.png', fullPage: true });
});

test('unknown upload result stops remaining work without automatic retry', async ({ page }) => {
  const kb = await prepare(page);
  let calls = 0;
  await page.route(`**/api/knowledge-bases/${kb}/documents`, async route => {
    calls++; await route.abort();
  });
  await page.getByLabel('选择文档', { exact: true }).setInputFiles([file('first.txt'), file('second.txt')]);
  await page.getByRole('button', { name: '上传文档', exact: true }).click();
  const results = page.getByRole('region', { name: '上传结果', exact: true });
  await expect(results).toContainText('结果待确认');
  await expect(results).toContainText('已停止 1');
  expect(calls).toBe(1);
});

test('stopping upload finishes current request, prevents duplicates and leaves later files untouched', async ({ page }) => {
  const kb = await prepare(page);
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let calls = 0;
  await page.route(`**/api/knowledge-bases/${kb}/documents`, async route => {
    calls++; await gate; await route.continue();
  });
  try {
    await page.getByLabel('选择文档', { exact: true }).setInputFiles([file('first.txt'), file('second.txt'), file('third.txt')]);
    await page.getByRole('button', { name: '上传文档', exact: true }).evaluate((button: HTMLButtonElement) => { button.click(); button.click(); });
    await expect(page.getByRole('button', { name: '上传并解析中', exact: true })).toBeDisabled();
    await expect(page.getByRole('button', { name: '刷新文档', exact: true })).toBeDisabled();
    await expect(page.getByRole('link', { name: '问答', exact: true })).toHaveAttribute('aria-disabled', 'true');
    await page.getByRole('button', { name: '停止后续上传', exact: true }).click();
    await expect(page.getByRole('button', { name: '等待当前文件完成', exact: true })).toBeDisabled();
    release();
    await expect(page.getByText('1 个文档', { exact: true })).toBeVisible();
    await expect(page.getByRole('region', { name: '上传结果' })).toContainText('已停止 2');
    expect(calls).toBe(1);
  } finally { release(); }
});

test('indexing reports failures and skips unparsed files without losing successes', async ({ page }) => {
  const kb = await prepare(page);
  const records: DocumentRecord[] = [];
  for (const candidate of [file('bad-index.txt'), file('good-index.txt'), { ...file('bad-parse.txt'), buffer: Buffer.from([255, 254]) }]) {
    records.push(await (await page.request.post(`/api/knowledge-bases/${kb}/documents`, { multipart: { file: candidate } })).json());
  }
  await page.getByRole('button', { name: '刷新文档', exact: true }).click();
  await expect(page.getByText('3 个文档', { exact: true })).toBeVisible();
  await page.route(`**/api/documents/${records[0].id}/index`, route => route.fulfill({ status: 409, json: { detail: '索引任务冲突' } }));
  await page.getByRole('checkbox', { name: '全选当前页', exact: true }).check();
  await page.getByRole('checkbox', { name: '选择 good-index.txt', exact: true }).uncheck();
  await expect(page.getByRole('checkbox', { name: '全选当前页', exact: true })).toHaveJSProperty('indeterminate', true);
  await page.getByRole('checkbox', { name: '全选当前页', exact: true }).check();
  await page.getByRole('button', { name: '批量建立索引', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '批量建立索引', exact: true });
  await expect(dialog).toContainText('将跳过：文档尚未成功解析');
  await dialog.getByRole('button', { name: '确认建立索引', exact: true }).click();
  await expect(dialog.getByText('成功 1', { exact: true })).toBeVisible();
  await expect(dialog.getByText('失败 1', { exact: true })).toBeVisible();
  await expect(dialog.getByText('已跳过 1', { exact: true })).toBeVisible();
  await expect(dialog).toContainText('索引任务冲突');
  await page.setViewportSize({ width: 390, height: 844 });
  const box = await dialog.boundingBox();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(390);
  await page.screenshot({ path: '../../work/batch-index-mobile.png', fullPage: true });
});

test('upload batch size is bounded and selection clears on pagination', async ({ page }) => {
  const kb = await prepare(page);
  const candidates = Array.from({ length: 21 }, (_, i) => file(`file-${i}.txt`));
  await page.getByLabel('选择文档', { exact: true }).setInputFiles(candidates);
  await expect(page.getByRole('alert').filter({ hasText: '一次最多选择 20' })).toBeVisible();
  await expect(page.getByRole('button', { name: '上传文档', exact: true })).toBeDisabled();
  for (const candidate of candidates) expect((await page.request.post(`/api/knowledge-bases/${kb}/documents`, { multipart: { file: candidate } })).status()).toBe(201);
  await page.getByRole('button', { name: '刷新文档', exact: true }).click();
  await expect(page.getByText('21 个文档', { exact: true })).toBeVisible();
  await page.getByRole('checkbox', { name: '全选当前页', exact: true }).check();
  await expect(page.getByText('已选择 20 个文档', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '下一页', exact: true }).click();
  await expect(page.getByText('第 2 / 2 页', { exact: true })).toBeVisible();
  await expect(page.getByRole('checkbox', { name: '全选当前页', exact: true })).not.toBeChecked();
  await expect(page.getByRole('button', { name: '批量删除', exact: true })).toHaveCount(0);
});

test('batch deletion cannot close while running and stops on authentication loss', async ({ page }) => {
  const kb = await prepare(page);
  const docs: DocumentRecord[] = [];
  for (const candidate of [file('first.txt'), file('second.txt')]) docs.push(await (await page.request.post(`/api/knowledge-bases/${kb}/documents`, { multipart: { file: candidate } })).json());
  await page.getByRole('button', { name: '刷新文档', exact: true }).click();
  await expect(page.getByText('2 个文档', { exact: true })).toBeVisible();
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let calls = 0;
  await page.route('**/api/documents/*', async route => {
    if (route.request().method() !== 'DELETE') return route.continue();
    calls++; await gate;
    await route.fulfill({ status: 401, json: { detail: '请先登录' } });
  });
  try {
    await page.getByRole('checkbox', { name: '全选当前页', exact: true }).check();
    await page.getByRole('button', { name: '批量删除', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: '批量删除文档', exact: true });
    await dialog.getByRole('button', { name: '确认删除', exact: true }).evaluate((button: HTMLButtonElement) => { button.click(); button.click(); });
    await expect(dialog.getByRole('button', { name: '停止后续任务', exact: true })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(dialog).toBeVisible();
    release();
    await expect(page).toHaveURL(/\/login$/);
    expect(calls).toBe(1);
  } finally { release(); }
});

test('retry uploads only known failed files, not earlier successes', async ({ page }) => {
  const kb = await prepare(page);
  const names: string[] = [];
  await page.route(`**/api/knowledge-bases/${kb}/documents`, async route => {
    const name = route.request().postDataBuffer()!.toString().match(/filename="([^"]+)"/)![1];
    names.push(name);
    if (names.length === 1) await route.fulfill({ status: 409, json: { detail: '临时冲突' } });
    else await route.continue();
  });
  await page.getByLabel('选择文档', { exact: true }).setInputFiles([file('retry.txt'), file('once.txt')]);
  await page.getByRole('button', { name: '上传文档', exact: true }).click();
  await expect(page.getByText('1 个文档', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '重试失败项', exact: true }).click();
  await expect(page.getByText('2 个文档', { exact: true })).toBeVisible();
  expect(names).toEqual(['retry.txt', 'once.txt', 'retry.txt']);
  await expect(page.getByRole('button', { name: '重试失败项', exact: true })).toHaveCount(0);
});

test('batch deletion reconciles already deleted files and falls back from the last page', async ({ page }) => {
  const kb = await prepare(page);
  const docs: DocumentRecord[] = [];
  for (let i = 0; i < 22; i++) docs.push(await (await page.request.post(`/api/knowledge-bases/${kb}/documents`, { multipart: { file: file(`doc-${i}.txt`) } })).json());
  await page.getByRole('button', { name: '刷新文档', exact: true }).click();
  await expect(page.getByText('22 个文档', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '下一页', exact: true }).click();
  await expect(page.getByText('第 2 / 2 页', { exact: true })).toBeVisible();
  await page.getByRole('checkbox', { name: '全选当前页', exact: true }).check();
  await page.getByRole('button', { name: '批量删除', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '批量删除文档', exact: true });
  const lastPage = (await (await page.request.get(`/api/knowledge-bases/${kb}/documents?limit=20&offset=20`)).json()).items;
  expect((await page.request.delete(`/api/documents/${lastPage[0].id}`)).status()).toBe(204);
  await dialog.getByRole('button', { name: '确认删除', exact: true }).click();
  await expect(dialog.getByText('成功 2', { exact: true })).toBeVisible();
  await expect(dialog).toContainText('文档已不存在');
  await dialog.getByRole('button', { name: '关闭', exact: true }).click();
  await expect(page.getByText('第 1 / 1 页', { exact: true })).toBeVisible();
  await expect(page.getByText('20 个文档', { exact: true })).toBeVisible();
});

test('all invalid selections explain each rejection before upload', async ({ page }) => {
  await prepare(page);
  await page.getByLabel('选择文档', { exact: true }).setInputFiles([file('unsupported.json'), file('empty.txt', '')]);
  await expect(page.getByRole('alert').filter({ hasText: 'unsupported.json' })).toContainText('只支持');
  await expect(page.getByRole('alert').filter({ hasText: 'empty.txt' })).toContainText('文件为空');
  await expect(page.getByRole('button', { name: '上传文档', exact: true })).toBeDisabled();
});

test('provider business failure pauses indexing instead of calling the same failing service repeatedly', async ({ page }) => {
  const kb = await prepare(page);
  const docs: DocumentRecord[] = [];
  for (const candidate of [file('first.txt'), file('second.txt')]) docs.push(await (await page.request.post(`/api/knowledge-bases/${kb}/documents`, { multipart: { file: candidate } })).json());
  await page.getByRole('button', { name: '刷新文档', exact: true }).click();
  await expect(page.getByText('2 个文档', { exact: true })).toBeVisible();
  let calls = 0;
  await page.route('**/api/documents/*/index', async route => {
    calls++;
    await route.fulfill({ json: { ...docs[0], index_status: 'failed', index_error: '模型服务请求频率受限，请稍后重试' } });
  });
  await page.getByRole('checkbox', { name: '全选当前页', exact: true }).check();
  await page.getByRole('button', { name: '批量建立索引', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '批量建立索引', exact: true });
  await dialog.getByRole('button', { name: '确认建立索引', exact: true }).click();
  await expect(dialog.getByText('已停止 1', { exact: true })).toBeVisible();
  await expect(dialog).toContainText('频率受限');
  expect(calls).toBe(1);
});
