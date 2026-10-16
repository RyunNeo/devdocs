import { test, expect } from "@playwright/test";
import path from "node:path";

test.use({ timezoneId: "Asia/Shanghai" });

async function register(page: import("@playwright/test").Page) {
  await page.goto("/register");
  await page.getByLabel("邮箱", { exact: true }).fill(`table-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`);
  await page.getByLabel("密码", { exact: true }).fill("Study-safe-2026!");
  await page.getByLabel("确认密码").fill("Study-safe-2026!");
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

test("table reads owned knowledge bases and sidebar follows navigation", async ({ page }) => {
  await register(page);
  const created = await page.request.post("/api/knowledge-bases", {
    data: { name: "React 学习", description: "我的组件与状态学习笔记" },
  });
  expect(created.status()).toBe(201);
  await page.getByRole("link", { name: "知识库", exact: true }).click();
  await expect(page).toHaveURL(/\/knowledge-bases$/);
  const row = page.getByRole("row").filter({ hasText: "React 学习" });
  await expect(row).toContainText("我的组件与状态学习笔记");
  await expect(page.getByRole("link", { name: "知识库", exact: true })).toHaveAttribute("aria-current", "page");
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await expect(row).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: path.resolve(`../../work/knowledge-table-${viewport.width}.png`), fullPage: true });
  }
  await page.getByRole("link", { name: "概览", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.reload();
  await expect(page.getByTestId("knowledge-base-count")).toHaveText("1");
});

test("new user has an empty table and logout prevents list access", async ({ page }) => {
  await register(page);
  await page.goto("/knowledge-bases");
  await expect(page.getByText("暂无知识库", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "退出登录" }).click();
  await page.goto("/knowledge-bases");
  await expect(page).toHaveURL(/\/login$/);
});

test("list failure can retry without showing a false empty state", async ({ page }) => {
  await register(page);
  let fail = true;
  await page.route("**/api/knowledge-bases?*", async (route) => {
    if (fail) await route.fulfill({ status: 503, json: { detail: "测试服务暂不可用" } });
    else await route.continue();
  });
  await page.goto("/knowledge-bases");
  await expect(page.getByRole("alert").filter({ hasText: "测试服务暂不可用" })).toBeVisible();
  await expect(page.getByText("暂无知识库", { exact: true })).toHaveCount(0);
  fail = false;
  await page.getByRole("button", { name: "刷新知识库" }).click();
  await expect(page.getByText("暂无知识库", { exact: true })).toBeVisible();
});

test("pagination requests the next offset and returns to first page", async ({ page }) => {
  await register(page);
  await page.route("**/api/knowledge-bases?*", async (route) => {
    const offset = Number(new URL(route.request().url()).searchParams.get("offset"));
    await route.fulfill({ json: {
      items: Array.from({ length: offset === 0 ? 20 : 1 }, (_, index) => ({
        id: `fixture-${offset + index}`, name: `主题 ${offset + index + 1}`,
        description: null, created_at: "2026-10-12T08:04:40Z", updated_at: "2026-10-12T08:04:40Z",
      })), total: 21, limit: 20, offset,
    } });
  });
  await page.goto("/knowledge-bases");
  await expect(page.getByRole("cell", { name: "主题 1", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "下一页" }).click();
  await expect(page.getByRole("cell", { name: "主题 21", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "下一页" })).toBeDisabled();
  await page.getByRole("button", { name: "上一页" }).click();
  await expect(page.getByRole("cell", { name: "主题 1", exact: true })).toBeVisible();
});

test("UTC and offset timestamps display the same Beijing time", async ({ page }) => {
  await register(page);
  await page.route("**/api/knowledge-bases?*", async (route) => {
    await route.fulfill({ json: {
      items: [
        { id: "without-zone", name: "UTC 无后缀", description: null, created_at: "2026-10-12T08:04:40", updated_at: "2026-10-12T08:04:40" },
        { id: "with-offset", name: "明确时区", description: null, created_at: "2026-10-12T16:04:40+08:00", updated_at: "2026-10-12T16:04:40+08:00" },
      ], total: 2, limit: 20, offset: 0,
    } });
  });
  await page.goto("/knowledge-bases");
  for (const name of ["UTC 无后缀", "明确时区"]) {
    await expect(page.getByRole("row").filter({ hasText: name })).toContainText("2026/10/12 16:04");
  }
});
