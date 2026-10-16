import { test, expect, type Page } from "@playwright/test";
import path from "node:path";

async function prepare(page: Page) {
  await page.goto("/register");
  await page.getByLabel("邮箱", { exact: true }).fill(`edit-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`);
  await page.getByLabel("密码", { exact: true }).fill("Study-safe-2026!");
  await page.getByLabel("确认密码").fill("Study-safe-2026!");
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  const response = await page.request.post("/api/knowledge-bases", { data: { name: "Python 学习", description: "原描述" } });
  expect(response.status()).toBe(201);
  const original = await response.json();
  await page.goto("/knowledge-bases");
  await page.getByRole("row").filter({ hasText: "Python 学习" }).getByRole("button", { name: "编辑" }).click();
  return original;
}

test("edit preloads fields and PATCH only renames without changing id or description", async ({ page }) => {
  const original = await prepare(page);
  const dialog = page.getByRole("dialog", { name: "编辑知识库" });
  await expect(dialog.getByLabel("名称", { exact: true })).toHaveValue("Python 学习");
  await expect(dialog.getByLabel("描述", { exact: true })).toHaveValue("原描述");
  await expect(dialog.getByRole("button", { name: "保存", exact: true })).toBeDisabled();
  const submitted: unknown[] = [];
  page.on("request", (request) => { if (request.method() === "PATCH") submitted.push(request.postDataJSON()); });
  await dialog.getByLabel("名称", { exact: true }).fill("Python 深入学习");
  await dialog.getByRole("button", { name: "保存", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("row").filter({ hasText: "Python 深入学习" })).toContainText("原描述");
  await expect(page.getByRole("row").filter({ hasText: "Python 深入学习" }).getByRole("button", { name: "编辑" })).toBeFocused();
  expect(submitted).toEqual([{ name: "Python 深入学习" }]);
  const current = await (await page.request.get(`/api/knowledge-bases/${original.id}`)).json();
  expect(current.id).toBe(original.id);
  expect(current.created_at).toBe(original.created_at);
});

test("clear description sends null while retaining the name", async ({ page }) => {
  const original = await prepare(page);
  const dialog = page.getByRole("dialog", { name: "编辑知识库" });
  await dialog.getByLabel("描述", { exact: true }).fill("");
  await dialog.getByRole("button", { name: "保存", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  const current = await (await page.request.get(`/api/knowledge-bases/${original.id}`)).json();
  expect(current.name).toBe("Python 学习");
  expect(current.description).toBeNull();
  await expect(page.getByRole("row").filter({ hasText: "Python 学习" })).toContainText("—");
});

test("whitespace-insensitive conflict preserves edits and cancel leaves stored data intact", async ({ page }) => {
  const original = await prepare(page);
  expect((await page.request.post("/api/knowledge-bases", { data: { name: "React 学习" } })).status()).toBe(201);
  const dialog = page.getByRole("dialog", { name: "编辑知识库" });
  await dialog.getByLabel("名称", { exact: true }).fill("React学习");
  await dialog.getByLabel("描述", { exact: true }).fill("保留草稿");
  await dialog.getByRole("button", { name: "保存", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("你已有同名知识库");
  await expect(dialog.getByLabel("名称", { exact: true })).toHaveValue("React学习");
  await expect(dialog.getByLabel("描述", { exact: true })).toHaveValue("保留草稿");
  await dialog.getByRole("button", { name: "取消" }).click();
  const current = await (await page.request.get(`/api/knowledge-bases/${original.id}`)).json();
  expect(current.name).toBe("Python 学习");
  expect(current.description).toBe("原描述");
});

test("edit dialog fits mobile and escape restores the row action focus", async ({ page }) => {
  await prepare(page);
  const dialog = page.getByRole("dialog", { name: "编辑知识库" });
  for (const size of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(size);
    const box = await dialog.boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(size.width);
    await page.screenshot({ path: path.resolve(`../../work/edit-modal-${size.width}.png`), fullPage: true });
  }
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("row").filter({ hasText: "Python 学习" }).getByRole("button", { name: "编辑" })).toHaveAccessibleName("编辑 Python 学习");
  await expect(page.getByRole("row").filter({ hasText: "Python 学习" }).getByRole("button", { name: "编辑" })).toBeFocused();
});

test("saved item from page two moves to the first page in updated-time order", async ({ page }) => {
  await prepare(page);
  await page.keyboard.press("Escape");
  const items = Array.from({ length: 21 }, (_, index) => ({
    id: `00000000-0000-0000-0000-${String(index + 1).padStart(12, "0")}`,
    name: `主题 ${index + 1}`, description: null,
    created_at: "2026-10-12T08:00:00Z", updated_at: "2026-10-12T08:00:00Z",
  }));
  let saved = false;
  await page.route("**/api/knowledge-bases?*", async (route) => {
    const offset = Number(new URL(route.request().url()).searchParams.get("offset"));
    const ordered = saved ? [items[20], ...items.slice(0, 20)] : items;
    await route.fulfill({ json: { items: ordered.slice(offset, offset + 20), total: 21, limit: 20, offset } });
  });
  await page.route("**/api/knowledge-bases/*", async (route) => {
    items[20].name = route.request().postDataJSON().name;
    items[20].updated_at = "2026-10-12T09:00:00Z";
    saved = true;
    await route.fulfill({ json: items[20] });
  });
  await page.getByRole("button", { name: "刷新知识库" }).click();
  await expect(page.getByRole("cell", { name: "主题 1", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "下一页" }).click();
  await page.getByRole("row").filter({ hasText: "主题 21" }).getByRole("button", { name: "编辑" }).click();
  const dialog = page.getByRole("dialog", { name: "编辑知识库" });
  await dialog.getByLabel("名称", { exact: true }).fill("主题 21 已编辑");
  await dialog.getByRole("button", { name: "保存", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText("第 1 / 2 页")).toBeVisible();
  await expect(page.getByRole("button", { name: "编辑 主题 21 已编辑", exact: true })).toBeFocused();
});
