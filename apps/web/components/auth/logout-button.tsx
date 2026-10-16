"use client";

import { LogOut, LoaderCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiRequest } from "@/lib/api";

export function LogoutButton() {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  async function logout() {
    setPending(true);
    setError("");
    try {
      await apiRequest("/auth/logout", {});
      router.replace("/login");
      router.refresh();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "退出失败，请重试");
      setPending(false);
    }
  }
  return (
    <div className="logout-control">
      <button className="text-button" onClick={logout} disabled={pending}>
        {pending ? <LoaderCircle size={16} className="spinner" /> : <LogOut size={16} />}
        退出登录
      </button>
      {error ? <p role="alert" className="form-error">{error}</p> : null}
    </div>
  );
}
