import { useCallback, useEffect, useRef, useState } from "react";
import { resetSessionApi, subscribeAgentStream } from "../lib/api";

export type StreamStatus = "idle" | "streaming" | "error" | "done";

function getOrCreateSessionId() {
  const key = "jarvis_session_id";
  let id = localStorage.getItem(key);
  if (!id) {
    id = (globalThis.crypto?.randomUUID?.() ?? String(Date.now())) as string;
    localStorage.setItem(key, id);
  }
  return id;
}

export function useAgentStream() {
  const [status, setStatus] = useState<StreamStatus>("idle");
  const [output, setOutput] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  const closeRef = useRef<null | (() => void)>(null);
  const sessionIdRef = useRef<string>(getOrCreateSessionId());

  // 탭 복귀 시: SSE 끊김 에러면 초기화 → 다음 메시지 보내면 재연결됨 (연결 버튼 불필요)
  useEffect(() => {
    function onVisible() {
      if (document.visibilityState !== "visible") return;
      setError(null);
      setStatus((s) => (s === "error" ? "done" : s));
    }
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, []);

  const stop = useCallback(() => {
    closeRef.current?.();
    closeRef.current = null;
    setStatus((s) => (s === "streaming" ? "done" : s));
  }, []);

  const resetSession = useCallback(async () => {
    await resetSessionApi(sessionIdRef.current);
    sessionIdRef.current = (globalThis.crypto?.randomUUID?.() ?? String(Date.now())) as string;
    localStorage.setItem("jarvis_session_id", sessionIdRef.current);
  }, []);

  const start = useCallback(
    (prompt: string, opts?: { reset?: boolean }) => {
      stop();
      setError(null);
      setStatus("streaming");
      setOutput((prev) => (prev ? `${prev}\n\nYou> ${prompt}\n\n` : `You> ${prompt}\n\n`));

      let receivedDone = false;

      const close = subscribeAgentStream(
        prompt,
        sessionIdRef.current,
        (evt) => {
          const raw = typeof evt.data === "string" ? evt.data : JSON.stringify(evt.data);
          let payload: { type?: string; text?: string; error?: string; ok?: boolean };
          try {
            payload = JSON.parse(raw);
          } catch {
            setOutput((prev) => prev + raw);
            return;
          }
          switch (payload.type) {
            case "chunk":
              if (payload.text != null) setOutput((prev) => prev + payload.text + "\n");
              break;
            case "done":
              receivedDone = true;
              setStatus("done");
              closeRef.current?.();
              closeRef.current = null;
              break;
            case "error":
              setError(payload.error ?? "알 수 없는 오류");
              setStatus("error");
              break;
            case "meta":
              // 연결 성공 메타; 무시
              break;
            default:
              setOutput((prev) => prev + raw + "\n");
          }
        },
        () => {
          // 서버가 연결을 닫으면 onerror가 호출됨. 이미 done 받았으면 무시
          if (!receivedDone) {
            setStatus("error");
            setError("SSE 연결 오류가 발생했습니다.");
          }
        },
        { reset: opts?.reset }
      );

      closeRef.current = close;
    },
    [stop]
  );

  return { status, output, error, start, stop, resetSession };
}
