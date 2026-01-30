import { useEffect, useMemo, useRef, useState } from "react";
import { useAgentStream } from "../hooks/useAgentStream";

type Mode = "disconnected" | "connected";

type Props = {
  onLogout?: () => void;
};

export default function AgentChat({ onLogout }: Props) {
  const [mode, setMode] = useState<Mode>("disconnected");
  const [prompt, setPrompt] = useState<string>("");
  const isComposingRef = useRef(false);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const { status, output, error, start, stop, resetSession } = useAgentStream();

  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [output, status]);

  const canConnect = useMemo(() => mode === "disconnected", [mode]);
  const canSend = useMemo(
    () => mode === "connected" && !!prompt.trim() && status !== "streaming",
    [mode, prompt, status]
  );

  const onConnect = () => {
    setMode("connected");
  };

  const onDisconnect = () => {
    stop();
    setMode("disconnected");
    setPrompt("");
  };

  const onSend = (valueFromInput?: string) => {
    // ✅ 사용자가 보낸 프롬프트도 응답창에 기록
    // (서버에서 "You>" 같은 의미없는 라인이 섞여와도, 최소한 사용자의 입력은 항상 남도록)
    const p = (valueFromInput !== undefined ? valueFromInput : prompt).trim();
    if (!p) return;
    start(p);
    setPrompt("");
  };

  return (
    <div
      style={{
        width: "100%",
        minHeight: "100vh",
        display: "flex",
        justifyContent: "center",
        boxSizing: "border-box",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 900,
          height: "100vh",
          display: "flex",
          flexDirection: "column",
          boxSizing: "border-box",
          overflow: "hidden",
        }}
      >
        {/* Top fixed header */}
        <div
          style={{
            position: "sticky",
            top: 0,
            zIndex: 10,
            background: "transparent",
            padding: 16,
            borderBottom: "1px solid rgba(0,0,0,0.08)",
          }}
        >
          <h2 style={{ margin: 0, marginBottom: 12 }}>Jarvis Agent</h2>

          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <button
              onClick={onConnect}
              disabled={!canConnect}
              style={{ padding: "10px 14px" }}
            >
              연결
            </button>

            <button
              onClick={stop}
              disabled={status !== "streaming"}
              style={{ padding: "10px 14px" }}
            >
              중지
            </button>

            <button
              onClick={onDisconnect}
              disabled={mode !== "connected"}
              style={{ padding: "10px 14px" }}
            >
              연결해제
            </button>

            <button
              onClick={() => resetSession()}
              disabled={mode !== "connected"}
              style={{ padding: "10px 14px" }}
              title="서버 세션을 끊고 다음 메시지부터 새 대화로 시작"
            >
              세션 초기화
            </button>

            {onLogout && (
              <button onClick={onLogout} style={{ padding: "10px 14px" }}>
                로그아웃
              </button>
            )}

            <div style={{ fontSize: 12, opacity: 0.8, marginLeft: "auto" }}>
              상태: {mode} / {status}
            </div>
          </div>

          {error && <div style={{ marginTop: 12, color: "crimson" }}>{error}</div>}
        </div>

        {/* Middle scroll area - 스크롤은 이 영역에만 */}
        <div
          ref={scrollContainerRef}
          style={{
            flex: 1,
            minHeight: 0,
            overflow: "auto",
            padding: 16,
          }}
        >
          <pre
            style={{
              margin: 0,
              padding: 12,
              background: "#111",
              color: "#eee",
              whiteSpace: "pre-wrap",
              borderRadius: 8,
            }}
          >
            {output || "(응답 대기 중)"}
          </pre>
        </div>

        {/* Bottom fixed input */}
        <div
          style={{
            position: "sticky",
            bottom: 0,
            background: "transparent",
            padding: 16,
            borderTop: "1px solid rgba(0,0,0,0.08)",
          }}
        >
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onCompositionStart={() => {
                isComposingRef.current = true;
              }}
              onCompositionEnd={(e) => {
                isComposingRef.current = false;
                setPrompt((e.target as HTMLInputElement).value);
              }}
              placeholder={
                mode === "connected"
                  ? "명령을 입력하세요"
                  : "먼저 연결을 누른 뒤 명령을 입력하세요"
              }
              disabled={mode !== "connected"}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  if (isComposingRef.current) {
                    e.preventDefault();
                    return;
                  }
                  e.preventDefault();
                  onSend((e.target as HTMLInputElement).value);
                }
              }}
              style={{ flex: 1, padding: 10 }}
            />

            <button
              onClick={() => onSend()}
              disabled={!canSend}
              style={{ padding: "10px 14px" }}
            >
              보내기
            </button>
          </div>
        </div>
      </div>
    </div>
    
  );
}
