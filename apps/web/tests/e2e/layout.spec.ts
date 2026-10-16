import { test, expect } from "@playwright/test";
import path from "node:path";

test("auth and workspace fit desktop and mobile screens", async ({ page }) => {
  const sizes = [{ width: 1440, height: 900 }, { width: 390, height: 844 }];
  for (const size of sizes) {
    await page.setViewportSize(size);
    await page.goto("/register");
    await expect(page.getByRole("heading", { name: "创建账号" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: path.resolve(`../../work/register-${size.width}.png`), fullPage: true });
  }
  await page.getByLabel("邮箱", { exact: true }).fill(`layout-${Date.now()}@example.com`);
  await page.getByLabel("密码", { exact: true }).fill("Study-safe-2026!");
  await page.getByLabel("确认密码").fill("Study-safe-2026!");
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  for (const size of sizes) {
    await page.setViewportSize(size);
    await expect(page.getByRole("heading", { name: "学习工作台" })).toBeVisible();
    await expect(page.getByText("服务连接正常")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: path.resolve(`../../work/dashboard-${size.width}.png`), fullPage: true });
  }
});
