"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Eye, EyeOff, LoaderCircle } from "lucide-react";
import { useState, type FormEvent } from "react";
import { apiRequest } from "@/lib/api";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const register = mode === "register";
  const router = useRouter();
  const [visible, setVisible] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setError("");
    const fields = new FormData(event.currentTarget);
    const email = String(fields.get("email")).trim();
    const password = String(fields.get("password"));
    if (register && password !== String(fields.get("confirmation"))) {
      setError("两次输入的密码不一致");
      return;
    }
    setPending(true);
    try {
      await apiRequest(`/auth/${mode}`, { email, password });
      router.replace("/dashboard");
      router.refresh();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "操作失败，请重试");
      setPending(false);
    }
  }
  return (
    <section className="auth-form-section">
      <p className="eyebrow">DEV DOCS / YOUR WORKSPACE</p>
      <h1>{register ? "创建账号" : "登录"}</h1>
      <p className="supporting">{register ? "开始你的技术文档学习之旅。" : "欢迎回来，继续你的学习。"}</p>
      <form onSubmit={submit} className="auth-form" aria-busy={pending}>
        <div className="field">
          <label htmlFor="email">邮箱</label>
          <input id="email" name="email" type="email" autoComplete="email" placeholder="you@example.com" required maxLength={320} disabled={pending} />
        </div>
        <div className="field">
          <label htmlFor="password">密码</label>
          <div className="password-field">
            <input id="password" name="password" type={visible ? "text" : "password"} autoComplete={register ? "new-password" : "current-password"} minLength={register ? 10 : 1} maxLength={128} placeholder={register ? "至少 10 个字符" : "输入你的密码"} required disabled={pending} aria-describedby={register ? "password-hint" : undefined} />
            <button type="button" className="icon-button password-toggle" onClick={() => setVisible(!visible)} aria-label={visible ? "隐藏密码" : "显示密码"} title={visible ? "隐藏密码" : "显示密码"} disabled={pending}>
              {visible ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>
          {register ? <small id="password-hint">10–128 个字符，建议包含字母、数字和符号。</small> : null}
        </div>
        {register ? <div className="field">
          <label htmlFor="confirmation">确认密码</label>
          <input id="confirmation" name="confirmation" type={visible ? "text" : "password"} autoComplete="new-password" required maxLength={128} disabled={pending} placeholder="再次输入密码" />
        </div> : null}
        {error ? <p role="alert" className="form-error">{error}</p> : null}
        <button className="primary-button" type="submit" disabled={pending}>
          {pending ? <LoaderCircle size={18} className="spinner" aria-hidden="true" /> : null}
          {pending ? "正在处理" : register ? "创建账号" : "登录"}
          {!pending ? <ArrowRight size={18} aria-hidden="true" /> : null}
        </button>
      </form>
      <p className="auth-switch">
        {register ? "已有账号？" : "还没有账号？"}
        <Link href={register ? "/login" : "/register"}>{register ? "登录" : "创建账号"}</Link>
      </p>
    </section>
  );
}
