import { test, expect, type Page } from "@playwright/test";
import path from "node:path";

async function prepare(page: Page) {
  await page.goto("/register");
  await page.getByLabel("邮箱", { exact: true }).fill(`upload-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`);
  await page.getByLabel("密码", { exact: true }).fill("Study-safe-2026!");
  await page.getByLabel("确认密码").fill("Study-safe-2026!");
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  const created = await page.request.post("/api/knowledge-bases", { data: { name: "上传练习" } });
  expect(created.status()).toBe(201);
  const kb = await created.json();
  await page.goto("/knowledge-bases");
  await page.getByRole("link", { name: "上传练习", exact: true }).click();
  await expect(page.getByRole("heading", { name: "上传练习", exact: true })).toBeVisible();
  return kb.id;
}

test("MD upload, escaped preview, duplicate prevention, TXT, totals and deletion", async ({ page }) => {
  await prepare(page);
  const content = "# React\n组件学习\n<script>window.uploadExecuted=true</script>";
  await page.getByLabel("选择文档").setInputFiles({ name: "react.md", mimeType: "text/markdown", buffer: Buffer.from(content) });
  await page.getByRole("button", { name: "上传文档", exact: true }).click();
  const row = page.getByRole("row").filter({ hasText: "react.md" });
  await expect(row).toContainText("已解析");
  await row.getByRole("button", { name: "预览 react.md", exact: true }).click();
  const preview = page.getByRole("dialog", { name: "react.md", exact: true });
  await expect(preview.locator("pre")).toHaveText(content);
  expect(await page.evaluate(() => "uploadExecuted" in window)).toBe(false);
  await page.keyboard.press("Escape");
  await page.getByLabel("选择文档").setInputFiles({ name: "renamed.txt", mimeType: "text/plain", buffer: Buffer.from(content) });
  await page.getByRole("button", { name: "上传文档", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "已有相同内容" })).toBeVisible();
  await page.getByLabel("选择文档").setInputFiles({ name: "python.txt", mimeType: "text/plain", buffer: Buffer.from("Python 函数与类") });
  await page.getByRole("button", { name: "上传文档", exact: true }).click();
  await expect(page.getByText("2 个文档", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "概览", exact: true }).click();
  await expect(page.getByTestId("document-count")).toHaveText("2");
  await page.goBack();
  await row.getByRole("button", { name: "删除 react.md", exact: true }).click();
  await page.getByRole("dialog", { name: "删除文档", exact: true }).getByRole("button", { name: "确认删除" }).click();
  await expect(page.getByText("1 个文档", { exact: true })).toBeVisible();
  await page.reload();
  await expect(row).toHaveCount(0);
});

test("bad encoding failure, reparse, rejected PDF and oversize file", async ({ page }) => {
  await prepare(page);
  const input = page.getByLabel("选择文档");
  await input.setInputFiles({ name: "bad.txt", mimeType: "text/plain", buffer: Buffer.from([255, 254]) });
  await page.getByRole("button", { name: "上传文档", exact: true }).click();
  const row = page.getByRole("row").filter({ hasText: "bad.txt" });
  await expect(row).toContainText("解析失败");
  await expect(row).toContainText("UTF-8");
  await row.getByRole("button", { name: "重新解析 bad.txt", exact: true }).click();
  await expect(row).toContainText("解析失败");
  await input.setInputFiles({ name: "a.json", mimeType: "application/json", buffer: Buffer.from("text") });
  await expect(page.getByRole("alert").filter({ hasText: "只支持" })).toBeVisible();
  await input.setInputFiles({ name: "large.txt", mimeType: "text/plain", buffer: Buffer.alloc(10 * 1024 * 1024 + 1, "a") });
  await expect(page.getByRole("alert").filter({ hasText: "10 MiB" })).toBeVisible();
  await expect(page.getByText("1 个文档", { exact: true })).toBeVisible();
});

test("mobile page and preview fit; missing knowledge base has clear state", async ({ page }) => {
  await prepare(page);
  await page.getByLabel("选择文档").setInputFiles({ name: "long-name-example.txt", mimeType: "text/plain", buffer: Buffer.from("paragraph ".repeat(2200)) });
  await page.getByRole("button", { name: "上传文档", exact: true }).click();
  await expect(page.getByText("1 个文档", { exact: true })).toBeVisible();
  for (const size of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(size);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(size.width);
    await page.screenshot({ path: path.resolve(`../../work/documents-${size.width}.png`), fullPage: true });
    await page.getByRole("button", { name: "预览 long-name-example.txt", exact: true }).click();
    const dialog = page.getByRole("dialog");
    const box = await dialog.boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(size.width);
    await expect(dialog).toContainText("预览已截断");
    await page.screenshot({ path: path.resolve(`../../work/document-preview-${size.width}.png`), fullPage: true });
    await page.keyboard.press("Escape");
    await expect(page.getByRole("button", { name: "预览 long-name-example.txt", exact: true })).toBeFocused();
  }
  await page.goto("/knowledge-bases/00000000-0000-0000-0000-000000000001");
  await expect(page.getByRole("heading", { name: "知识库不存在或无法访问" })).toBeVisible();
});

test("upload pending prevents repeats and network failure allows confirming list before retry", async ({ page }) => {
  const kb = await prepare(page);
  let requests = 0;
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  await page.route(`**/api/knowledge-bases/${kb}/documents`, async (route) => {
    requests++;
    expect(route.request().headers()["content-type"]).toMatch(/^multipart\/form-data; boundary=/);
    await gate;
    await route.abort();
  });
  const input = page.getByLabel("选择文档");
  await input.setInputFiles({ name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("network-test") });
  await page.getByRole("button", { name: "上传文档", exact: true }).evaluate((button: HTMLButtonElement) => {
    button.click(); button.click(); button.click();
  });
  await expect(page.getByRole("button", { name: "上传并解析中" })).toBeDisabled();
  await expect(input).toBeDisabled();
  release();
  await expect(page.getByRole("alert").filter({ hasText: "请刷新文档列表确认" })).toBeVisible();
  expect(requests).toBe(1);
  await page.unroute(`**/api/knowledge-bases/${kb}/documents`);
  await page.getByRole("button", { name: "刷新文档" }).click();
  await expect(page.getByText("0 个文档", { exact: true })).toBeVisible();
  await input.setInputFiles({ name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("network-test") });
  await page.getByRole("button", { name: "上传文档", exact: true }).click();
  await expect(page.getByText("1 个文档", { exact: true })).toBeVisible();
});

test("exactly 10 MiB reaches the API intact through the Next rewrite", async ({ page }) => {
  test.setTimeout(60000);
  await prepare(page);
  await page.getByLabel("选择文档").setInputFiles({ name: "boundary.txt", mimeType: "text/plain", buffer: Buffer.alloc(10 * 1024 * 1024, "a") });
  const uploaded = page.waitForResponse((response) => response.request().method() === "POST" && response.url().endsWith("/documents"));
  await page.getByRole("button", { name: "上传文档", exact: true }).click();
  const response = await uploaded;
  expect(response.status()).toBe(201);
  const doc = await response.json();
  expect(doc.size_bytes).toBe(10 * 1024 * 1024);
  expect(doc.character_count).toBe(10 * 1024 * 1024);
  expect(doc.status).toBe("parsed");
});
