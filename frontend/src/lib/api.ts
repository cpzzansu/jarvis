const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  (typeof window !== "undefined" ? window.location.origin : "http://localhost:8787");

const fetchOpts: RequestInit = { credentials: "include" };

export type AgentStreamEvent = {
  raw: string;
  data?: any;
};

// ---------- Auth ----------
export type LoginResponse = { ok: boolean; email?: string };
export type MeResponse = { ok: boolean; email?: string };

export async function loginApi(email: string, password: string): Promise<LoginResponse> {
  const res = await fetch(`${API_BASE_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
    ...fetchOpts,
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error((d as { detail?: string }).detail ?? "Login failed");
  }
  return res.json();
}

export async function logoutApi(): Promise<void> {
  await fetch(`${API_BASE_URL}/api/auth/logout`, { method: "POST", ...fetchOpts });
}

export async function meApi(): Promise<MeResponse | null> {
  const res = await fetch(`${API_BASE_URL}/api/auth/me`, fetchOpts);
  if (res.status === 401) return null;
  if (!res.ok) return null;
  return res.json();
}

// ---------- Agent ----------
export async function resetSessionApi(sessionId: string): Promise<void> {
  const url = new URL("/api/agent/session/reset", API_BASE_URL);
  url.searchParams.set("session_id", sessionId);
  await fetch(url.toString(), fetchOpts);
}

export function buildAgentStreamUrl(prompt: string, sessionId: string, reset?: boolean) {
  const url = new URL("/api/agent/stream", API_BASE_URL);
  url.searchParams.set("prompt", prompt);
  url.searchParams.set("session_id", sessionId);
  if (reset) url.searchParams.set("reset", "true");
  return url.toString();
}

/**
 * SSE 스트림을 구독합니다.
 * - onMessage: 서버가 보내는 message 이벤트(data)를 전달
 * - onError: 에러 발생 시 호출
 *
 * 반환값: close() 함수
 */
export function subscribeAgentStream(
  prompt: string,
  sessionId: string,
  onMessage: (evt: MessageEvent) => void,
  onError?: (err: any) => void,
  opts?: { reset?: boolean }
) {
  const es = new EventSource(buildAgentStreamUrl(prompt, sessionId, opts?.reset));
  es.onmessage = onMessage;
  es.onerror = (e) => {
    onError?.(e);
    // 브라우저가 자동 재연결을 시도할 수 있어, 여기서 즉시 close하지는 않음
  };

  return () => es.close();
}
