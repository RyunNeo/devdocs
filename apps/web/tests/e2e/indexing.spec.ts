import { test, expect, type Page } from "@playwright/test";
import path from "node:path";

async function prepare(page: Page) {
  await page.goto("/register");
  await page.getByLabel("邮箱", { exact: true }).fill(`index-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`);
  await page.getByLabel("密码", { exact: true }).fill("Study-safe-2026!");
  await page.getByLabel("确认密码").fill("Study-safe-2026!");
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  const response = await page.request.post("/api/knowledge-bases", { data: { name: "索引练习" } });
  const kb = await response.json();
  const uploaded = await page.request.post(`/api/knowledge-bases/${kb.id}/documents`, { multipart: {
    file: { name: "notes.md", mimeType: "text/markdown", buffer: Buffer.from("# Python\n\n## Functions\n\n" + "函数与类型。".repeat(1000)) },
  } });
  expect(uploaded.status()).toBe(201);
  const doc = await uploaded.json();
  await page.goto(`/knowledge-bases/${kb.id}`);
  await expect(page.getByText("1 个文档", { exact: true })).toBeVisible();
  return doc;
}

test("index confirmation, completed state, chunk source preview and idempotency", async ({ page }) => {
  const doc = await prepare(page);
  const button = page.getByRole("button", { name: "建立索引 notes.md", exact: true });
  await button.click();
  const dialog = page.getByRole("dialog", { name: "建立文档索引", exact: true });
  await expect(dialog).toContainText("硅基流动");
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  expect((await (await page.request.get(`/api/documents/${doc.id}`)).json()).index_status).toBe("pending");
  await button.click();
  await dialog.getByRole("button", { name: "确认建立索引", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("row").filter({ hasText: "notes.md" })).toContainText("可检索");
  const first = await (await page.request.get(`/api/documents/${doc.id}/chunks`)).json();
  expect(first.total).toBeGreaterThan(1);
  await page.getByRole("button", { name: "查看片段 notes.md", exact: true }).click();
  const chunks = page.getByRole("dialog", { name: "文档片段", exact: true });
  await expect(chunks).toContainText("BAAI/bge-m3");
  await expect(chunks).toContainText("1024");
  await expect(chunks).toContainText("Functions");
  await page.keyboard.press("Escape");
  await button.click();
  await dialog.getByRole("button", { name: "确认建立索引", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  const second = await (await page.request.get(`/api/documents/${doc.id}/chunks`)).json();
  expect(second.items.map((item: { id: string }) => item.id)).toEqual(first.items.map((item: { id: string }) => item.id));
});

test("PDF parses and chunks retain page numbers; image-only PDF fails clearly", async ({ page }) => {
  await prepare(page);
  await page.getByLabel("选择文档").setInputFiles(path.resolve("../../work/stage3-text.pdf"));
  await page.getByRole("button", { name: "上传文档", exact: true }).click();
  await expect(page.getByRole("row").filter({ hasText: "stage3-text.pdf" })).toContainText("已解析");
  await page.getByRole("button", { name: "建立索引 stage3-text.pdf", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "确认建立索引", exact: true }).click();
  await page.getByRole("button", { name: "查看片段 stage3-text.pdf", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "文档片段", exact: true });
  await expect(dialog).toContainText("第 1 页");
  await expect(dialog).toContainText("第 2 页");
  await page.keyboard.press("Escape");
  await page.getByLabel("选择文档").setInputFiles(path.resolve("../../work/stage3-scan.pdf"));
  await page.getByRole("button", { name: "上传文档", exact: true }).click();
  await expect(page.getByRole("row").filter({ hasText: "stage3-scan.pdf" })).toContainText("扫描件");
});

test("configuration errors stay visible and mobile index/chunks dialogs fit", async ({ page }) => {
  const doc = await prepare(page);
  await page.route(`**/api/documents/${doc.id}/index`, (route) => route.fulfill({ status: 503, json: { detail: "请先在后端配置 SILICONFLOW_API_KEY" } }));
  await page.getByRole("button", { name: "建立索引 notes.md", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "建立文档索引", exact: true });
  await dialog.getByRole("button", { name: "确认建立索引", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("SILICONFLOW_API_KEY");
  await page.setViewportSize({ width: 390, height: 844 });
  const box = await dialog.boundingBox();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(390);
  await page.screenshot({ path: path.resolve("../../work/index-confirm-390.png"), fullPage: true });
  await dialog.getByRole("button", { name: "取消" }).click();
  await page.unroute(`**/api/documents/${doc.id}/index`);
  await page.getByRole("button", { name: "建立索引 notes.md", exact: true }).click();
  await dialog.getByRole("button", { name: "确认建立索引", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await page.screenshot({ path: path.resolve("../../work/index-table-390.png"), fullPage: true });
  await page.getByRole("button", { name: "查看片段 notes.md", exact: true }).click();
  const chunks = page.getByRole("dialog", { name: "文档片段", exact: true });
  await expect(chunks).toContainText("Functions");
  await page.screenshot({ path: path.resolve("../../work/index-chunks-390.png"), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("failed rebuilding retains old chunks without displaying ready", async ({ page }) => {
  const original = await prepare(page);
  await page.getByRole("button", { name: "建立索引 notes.md", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "建立文档索引", exact: true });
  await dialog.getByRole("button", { name: "确认建立索引", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  const completed = await (await page.request.get(`/api/documents/${original.id}`)).json();
  const failed = { ...completed, index_status: "failed", index_error: "模型服务暂不可用，请稍后重试" };
  await page.route(`**/api/documents/${original.id}/index`, (route) => route.fulfill({ json: failed }));
  await page.route(`**/api/knowledge-bases/${original.knowledge_base_id}/documents?*`, (route) => route.fulfill({ json: { items: [failed], total: 1, limit: 20, offset: 0 } }));
  await page.getByRole("button", { name: "建立索引 notes.md", exact: true }).click();
  await dialog.getByRole("button", { name: "确认建立索引", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  const row = page.getByRole("row").filter({ hasText: "notes.md" });
  await expect(row).toContainText("索引失败");
  await expect(row.getByText("可检索", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "查看片段 notes.md", exact: true })).toBeEnabled();
});

test("pending index blocks repeated requests and cancellation", async ({ page }) => {
  const doc = await prepare(page);
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  let calls = 0;
  await page.route(`**/api/documents/${doc.id}/index`, async (route) => {
    calls++; await gate;
    await route.fulfill({ json: { ...doc, index_status: "failed", index_error: "模型请求超时" } });
  });
  await page.getByRole("button", { name: "建立索引 notes.md", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "建立文档索引", exact: true });
  await dialog.getByRole("button", { name: "确认建立索引", exact: true }).evaluate((button: HTMLButtonElement) => { button.click(); button.click(); button.click(); });
  await expect(dialog.getByRole("button", { name: "正在建立索引" })).toBeDisabled();
  await expect(dialog.getByRole("button", { name: "取消", exact: true })).toBeDisabled();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeVisible();
  release();
  await expect(dialog).toHaveCount(0);
  expect(calls).toBe(1);
  await expect(page.getByRole("status").filter({ hasText: "索引失败" })).toBeVisible();
});
