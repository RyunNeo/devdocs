import { test, expect, type Page } from "@playwright/test";
import path from "node:path";

async function prepare(page: Page, warmDashboard = false) {
  await page.goto("/register");
  await page.getByLabel("邮箱", { exact: true }).fill(`delete-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`);
  await page.getByLabel("密码", { exact: true }).fill("Study-safe-2026!");
  await page.getByLabel("确认密码").fill("Study-safe-2026!");
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  const response = await page.request.post("/api/knowledge-bases", { data: { name: "删除练习", description: "测试记录" } });
  expect(response.status()).toBe(201);
  const original = await response.json();
  if (warmDashboard) {
    await page.goto("/dashboard");
    await expect(page.getByTestId("knowledge-base-count")).toHaveText("1");
  }
  await page.goto("/knowledge-bases");
  await page.getByRole("button", { name: "删除 删除练习", exact: true }).click();
  return original;
}

test("cancel and escape preserve data; confirmed deletion updates empty list and dashboard", async ({ page }) => {
  const original = await prepare(page, true);
  const dialog = page.getByRole("dialog", { name: "删除知识库", exact: true });
  await expect(dialog).toContainText("删除练习");
  await expect(dialog.getByRole("button", { name: "取消", exact: true })).toBeFocused();
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  await expect(page.getByRole("button", { name: "删除 删除练习", exact: true })).toBeFocused();
  expect((await page.request.get(`/api/knowledge-bases/${original.id}`)).status()).toBe(200);
  await page.getByRole("button", { name: "删除 删除练习", exact: true }).click();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("button", { name: "删除 删除练习", exact: true })).toBeFocused();
  await page.getByRole("button", { name: "删除 删除练习", exact: true }).click();
  await dialog.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText("0 个知识库", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "暂无知识库" })).toBeVisible();
  await expect(page.getByRole("button", { name: "刷新知识库" })).toBeFocused();
  expect((await page.request.get(`/api/knowledge-bases/${original.id}`)).status()).toBe(404);
  await page.getByRole("link", { name: "概览", exact: true }).click();
  await expect(page.getByTestId("knowledge-base-count")).toHaveText("0");
  await expect(page.getByText("删除练习", { exact: true })).toHaveCount(0);
});

test("pending deletion blocks cancellation and duplicate submission; errors allow retry", async ({ page }) => {
  const original = await prepare(page);
  let requests = 0;
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  await page.route(`**/api/knowledge-bases/${original.id}`, async (route) => {
    requests++;
    await gate;
    await route.fulfill({ status: 503, json: { detail: "服务暂不可用，请稍后重试" } });
  });
  const dialog = page.getByRole("dialog", { name: "删除知识库", exact: true });
  await dialog.getByRole("button", { name: "确认删除", exact: true }).evaluate((button: HTMLButtonElement) => {
    button.click(); button.click(); button.click();
  });
  await expect(dialog.getByRole("button", { name: "正在删除" })).toBeDisabled();
  await expect(dialog.getByRole("button", { name: "取消" })).toBeDisabled();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeVisible();
  release();
  await expect(dialog.getByRole("alert")).toContainText("服务暂不可用");
  expect(requests).toBe(1);
  await page.unroute(`**/api/knowledge-bases/${original.id}`);
  await dialog.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(page.getByText("0 个知识库", { exact: true })).toBeVisible();
});

test("unknown network result asks to refresh; missing record reconciles stale list", async ({ page }) => {
  const original = await prepare(page);
  await page.route(`**/api/knowledge-bases/${original.id}`, (route) => route.abort());
  const dialog = page.getByRole("dialog", { name: "删除知识库", exact: true });
  await dialog.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("请刷新列表确认");
  await page.unroute(`**/api/knowledge-bases/${original.id}`);
  expect((await page.request.delete(`/api/knowledge-bases/${original.id}`)).status()).toBe(204);
  await dialog.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText("0 个知识库", { exact: true })).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "知识库已不存在" })).toBeVisible();
});

test("expired session redirects deletion to login", async ({ page }) => {
  await prepare(page);
  expect((await page.request.post("/api/auth/logout")).status()).toBe(204);
  await page.getByRole("dialog").getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
});

test("deleting sole item on last page falls back and restores focus; mobile dialog fits", async ({ page }) => {
  await prepare(page);
  await page.keyboard.press("Escape");
  let items = Array.from({ length: 21 }, (_, i) => ({ id: String(i), name: `主题 ${i + 1}`, description: null, created_at: "2026-10-12T08:00:00Z", updated_at: "2026-10-12T08:00:00Z" }));
  await page.route("**/api/knowledge-bases?*", async (route) => {
    const offset = Number(new URL(route.request().url()).searchParams.get("offset"));
    await route.fulfill({ json: { items: items.slice(offset, offset + 20), total: items.length, limit: 20, offset } });
  });
  await page.route("**/api/knowledge-bases/20", async (route) => {
    expect(route.request().method()).toBe("DELETE");
    items = items.slice(0, 20);
    await route.fulfill({ status: 204 });
  });
  await page.getByRole("button", { name: "刷新知识库" }).click();
  await page.getByRole("button", { name: "下一页" }).click();
  await page.getByRole("button", { name: "删除 主题 21", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "删除知识库", exact: true });
  for (const size of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(size);
    const box = await dialog.boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(size.width);
    await page.screenshot({ path: path.resolve(`../../work/delete-modal-${size.width}.png`), fullPage: true });
  }
  await dialog.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(page.getByText("第 1 / 1 页")).toBeVisible();
  await expect(page.getByText("20 个知识库", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "刷新知识库" })).toBeFocused();
});

test("deletion retains a nonempty second page and visible mobile actions", async ({ page }) => {
  await prepare(page);
  await page.keyboard.press("Escape");
  let items = Array.from({ length: 22 }, (_, i) => ({ id: String(i), name: `主题 ${i + 1}`, description: null, created_at: "2026-10-12T08:00:00Z", updated_at: "2026-10-12T08:00:00Z" }));
  await page.route("**/api/knowledge-bases?*", async (route) => {
    const offset = Number(new URL(route.request().url()).searchParams.get("offset"));
    await route.fulfill({ json: { items: items.slice(offset, offset + 20), total: items.length, limit: 20, offset } });
  });
  await page.route("**/api/knowledge-bases/20", async (route) => {
    items = items.filter((item) => item.id !== "20");
    await route.fulfill({ status: 204 });
  });
  await page.getByRole("button", { name: "刷新知识库" }).click();
  await page.getByRole("button", { name: "下一页" }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  const editBox = await page.getByRole("button", { name: "编辑 主题 21", exact: true }).boundingBox();
  const deleteButton = page.getByRole("button", { name: "删除 主题 21", exact: true });
  const deleteBox = await deleteButton.boundingBox();
  expect(editBox!.x + editBox!.width).toBeLessThanOrEqual(deleteBox!.x);
  expect(deleteBox!.x + deleteBox!.width).toBeLessThanOrEqual(390);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: path.resolve("../../work/delete-table-390.png"), fullPage: true });
  await deleteButton.click();
  await page.getByRole("dialog").getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(page.getByText("第 2 / 2 页")).toBeVisible();
  await expect(page.getByRole("cell", { name: "主题 22", exact: true })).toBeVisible();
  await expect(page.getByText("21 个知识库", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "刷新知识库" })).toBeFocused();
});
