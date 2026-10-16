import { test, expect } from "@playwright/test";
import path from "node:path";

async function openList(page: import("@playwright/test").Page) {
  await page.goto("/register");
  await page.getByLabel("邮箱", { exact: true }).fill(`create-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`);
  await page.getByLabel("密码", { exact: true }).fill("Study-safe-2026!");
  await page.getByLabel("确认密码").fill("Study-safe-2026!");
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.goto("/knowledge-bases");
  await expect(page.getByText("暂无知识库", { exact: true })).toBeVisible();
}

test("create modal saves a real knowledge base and refreshes the table", async ({ page }) => {
  await openList(page);
  await page.getByRole("button", { name: "创建知识库", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "创建知识库" });
  await expect(dialog.getByLabel("名称", { exact: true })).toBeFocused();
  await dialog.getByLabel("名称", { exact: true }).fill("  Python 学习  ");
  await dialog.getByLabel("描述", { exact: true }).fill("我的 Python 与 AI 学习笔记");
  await dialog.getByRole("button", { name: "创建", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("row").filter({ hasText: "Python 学习" })).toContainText("我的 Python 与 AI 学习笔记");
  await expect(page.getByRole("status")).toContainText("1 个知识库");
});

test("duplicate error preserves input and a different name can be submitted", async ({ page }) => {
  await openList(page);
  expect((await page.request.post("/api/knowledge-bases", { data: { name: "React 学习" } })).status()).toBe(201);
  await page.getByRole("button", { name: "创建知识库", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "创建知识库" });
  await dialog.getByLabel("名称", { exact: true }).fill("REACT学习");
  await dialog.getByLabel("描述", { exact: true }).fill("保留输入内容");
  await dialog.getByRole("button", { name: "创建", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("你已有同名知识库");
  await expect(dialog.getByLabel("名称", { exact: true })).toHaveValue("REACT学习");
  await expect(dialog.getByLabel("描述", { exact: true })).toHaveValue("保留输入内容");
  await dialog.getByLabel("名称", { exact: true }).fill("React 练习");
  await dialog.getByRole("button", { name: "创建", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("row").filter({ hasText: "React 练习" })).toContainText("保留输入内容");
});

test("cancel and escape do not create data and mobile modal fits", async ({ page }) => {
  await openList(page);
  const trigger = page.getByRole("button", { name: "创建知识库", exact: true });
  await trigger.click();
  let dialog = page.getByRole("dialog", { name: "创建知识库" });
  await dialog.getByLabel("名称", { exact: true }).fill("不会创建");
  await dialog.getByRole("button", { name: "取消" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await expect(page.getByText("暂无知识库", { exact: true })).toBeVisible();
  await trigger.click();
  dialog = page.getByRole("dialog", { name: "创建知识库" });
  for (const size of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(size);
    await expect(dialog).toBeVisible();
    const box = await dialog.boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(size.width);
    await page.screenshot({ path: path.resolve(`../../work/create-modal-${size.width}.png`), fullPage: true });
  }
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test("blank trimmed name is rejected before sending and description is optional", async ({ page }) => {
  await openList(page);
  let posts = 0;
  page.on("request", (request) => { if (request.method() === "POST" && request.url().endsWith("/api/knowledge-bases")) posts++; });
  await page.getByRole("button", { name: "创建知识库", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "创建知识库" });
  await dialog.getByLabel("名称", { exact: true }).fill("   ");
  await dialog.getByRole("button", { name: "创建", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("请输入知识库名称");
  expect(posts).toBe(0);
  await dialog.getByLabel("名称", { exact: true }).fill("无描述知识库");
  await dialog.getByRole("button", { name: "创建", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("row").filter({ hasText: "无描述知识库" })).toContainText("—");
});

test("pending submit prevents duplicate requests and blocks closing until completion", async ({ page }) => {
  await openList(page);
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  let requests = 0;
  await page.route("**/api/knowledge-bases", async (route) => {
    requests++;
    await gate;
    await route.continue();
  });
  await page.getByRole("button", { name: "创建知识库", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "创建知识库" });
  await dialog.getByLabel("名称", { exact: true }).fill("仅一次请求");
  await dialog.getByRole("button", { name: "创建", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "正在创建" })).toBeDisabled();
  await expect(dialog.getByRole("button", { name: "取消" })).toBeDisabled();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeVisible();
  expect(requests).toBe(1);
  release();
  await expect(dialog).toHaveCount(0);
});
