import { test, expect } from "@playwright/test";

test("protected dashboard redirects to login", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "登录" })).toBeVisible();
});

test("register, refresh, logout and login", async ({ page }) => {
  const email = `learner-${Date.now()}@example.com`;
  await page.goto("/register");
  await page.getByLabel("邮箱", { exact: true }).fill(email);
  await page.getByLabel("密码", { exact: true }).fill("Study-safe-2026!");
  await page.getByLabel("确认密码").fill("Study-safe-2026!");
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByTestId("account-email")).toHaveText(email);
  await page.reload();
  await expect(page.getByTestId("account-email")).toHaveText(email);
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("邮箱", { exact: true }).fill(email);
  await page.getByLabel("密码", { exact: true }).fill("wrong-password");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "邮箱或密码错误" })).toBeVisible();
  await page.getByLabel("密码", { exact: true }).fill("Study-safe-2026!");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
});

test("password confirmation prevents registration", async ({ page }) => {
  await page.goto("/register");
  await page.getByLabel("邮箱", { exact: true }).fill("mismatch@example.com");
  await page.getByLabel("密码", { exact: true }).fill("Study-safe-2026!");
  await page.getByLabel("确认密码").fill("different-password");
  await page.getByRole("button", { name: "创建账号" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "两次输入的密码不一致" })).toBeVisible();
  await expect(page).toHaveURL(/\/register$/);
});
