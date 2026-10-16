export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

export async function apiRequest<T>(path: string, body?: unknown, signal?: AbortSignal, method?: "POST" | "PATCH" | "DELETE"): Promise<T> {
  let response: Response;
  try {
    const multipart = body instanceof FormData;
    response = await fetch(`/api${path}`, {
      method: method ?? (body === undefined ? "GET" : "POST"),
      credentials: "same-origin",
      headers: body === undefined || multipart ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : multipart ? body : JSON.stringify(body),
      cache: "no-store",
      signal,
    });
  } catch {
    throw new ApiError("暂时无法连接服务，请稍后重试", 0);
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new ApiError(
      response.status === 413 ? "文件或上传请求超过大小限制，单个文件最多 10 MiB"
        : typeof payload?.detail === "string" ? payload.detail : "服务暂不可用，请稍后重试",
      response.status,
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
