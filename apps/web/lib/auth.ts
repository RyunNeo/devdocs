import "server-only";
import { cookies } from "next/headers";
import { cache } from "react";

export type User = {
  id: string;
  email: string;
  plan: string;
  created_at: string;
};

export const getCurrentUser = cache(async (): Promise<User | null> => {
  const cookieStore = await cookies();
  const name = process.env.SESSION_COOKIE_NAME ?? "devdocs_session";
  const cookie = cookieStore.get(name);
  if (!cookie) return null;
  let response: Response;
  try {
    response = await fetch(`${process.env.API_BASE_URL ?? "http://127.0.0.1:8000"}/auth/me`, {
      headers: { Cookie: `${name}=${cookie.value}` },
      cache: "no-store",
      signal: AbortSignal.timeout(7000),
    });
  } catch {
    throw new Error("身份服务暂不可用，请检查后端和数据库");
  }
  if (response.status === 401) return null;
  if (!response.ok) throw new Error("身份服务暂不可用，请检查后端和数据库");
  return response.json();
});
