import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AdvisorState, api, TranscriptEntry } from "../api";
import BundleCard from "../components/BundleCard";
import GuidedAdvisor from "../components/GuidedAdvisor";

const SESSION_KEY = "udyam_session";

// The model writes light markdown: render **bold** and drop heading marks, never inject HTML.
function renderInline(line: string) {
  const text = line.replace(/^#{1,6}\s+/, "");
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4
      ? <strong key={i}>{part.slice(2, -2)}</strong>
      : <span key={i}>{part.replace(/\*\*/g, "")}</span>);
}
type Mode = "chat" | "guided";

export default function Advisor() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const partner = params.get("partner");   // assisted mode: a channel partner fills the journey for the owner
  const [state, setState] = useState<AdvisorState | null>(null);
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("chat");
  const [llmOk, setLlmOk] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);

  // create or resume the session; pick the mode from whether the chat model is available
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const health = await api.health().catch(() => ({ llm_available: false }));
        if (!health.llm_available) {
          setLlmOk(false);
          setMode("guided");
        }
        const existing = sessionStorage.getItem(SESSION_KEY);
        let s: AdvisorState;
        if (existing) {
          s = await api.getSession(existing);
        } else {
          s = await api.newSession(partner ?? undefined);
          sessionStorage.setItem(SESSION_KEY, s.session_id);
        }
        if (cancelled) return;
        setState(s);
        setTranscript(s.transcript);
        const first = sessionStorage.getItem("udyam_first_message");
        if (first && s.transcript.length === 0 && health.llm_available) {
          sessionStorage.removeItem("udyam_first_message");
          await send(first, s.session_id);
        }
      } catch (e) {
        setError(String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcript, busy]);

  async function send(text: string, sessionId?: string) {
    const id = sessionId ?? state?.session_id;
    const message = text.trim();
    if (!id || !message || busy) return;
    setBusy(true);
    setError(null);
    setInput("");
    setTranscript((t) => [...t, { role: "user", text: message }]);
    try {
      const s = await api.sendMessage(id, message);
      setState(s);
      setTranscript(s.transcript);
    } catch (e) {
      const msg = String(e);
      setTranscript((t) => t.slice(0, -1));
      if (msg.includes("llm_unavailable")) {
        // no key or no credit: fall back to the tap-to-answer advisor, same engine and prices
        setLlmOk(false);
        setMode("guided");
        setError("The chat advisor is offline right now, so we switched to quick answers. Your bundle and prices are the same.");
      } else {
        setError("The advisor could not reply. " + msg);
      }
    } finally {
      setBusy(false);
    }
  }

  function restart() {
    sessionStorage.removeItem(SESSION_KEY);
    window.location.reload();
  }

  const rec = state?.recommendation ?? null;

  return (
    <div className="page advisor">
      <div className="mode-bar">
        <div className="seg">
          <button className={mode === "chat" ? "on" : ""} disabled={!llmOk} onClick={() => setMode("chat")} title={llmOk ? "" : "Chat needs the AI service"}>
            Type freely
          </button>
          <button className={mode === "guided" ? "on" : ""} onClick={() => setMode("guided")}>Tap answers</button>
        </div>
        <button type="button" className="icon" title="Start over" onClick={restart}>↺</button>
      </div>
      {partner && <div className="banner info mode-banner">Assisted mode: partner {partner} is filling this in with the customer.</div>}
      {error && <div className="banner info mode-banner">{error}</div>}

      {mode === "guided" && state ? (
        <div className="chat">
          <GuidedAdvisor session={state} onState={(s) => { setState(s); setTranscript(s.transcript); }} />
        </div>
      ) : (
        <>
          <div className="chat">
            {transcript.length === 0 && !busy && (
              <div className="bubble assistant">
                Namaste! I am the Accel Business advisor. Tell me about your business in English, हिंदी or Hinglish,
                and I will suggest the right bundle with one clear monthly price.
              </div>
            )}
            {transcript.map((m, i) => (
              <div key={i} className={`bubble ${m.role}`}>
                {m.text.split("\n").map((line, j) => <p key={j}>{renderInline(line)}</p>)}
              </div>
            ))}
            {busy && <div className="bubble assistant typing"><span /><span /><span /></div>}
            {rec && (
              <div className="card-wrap">
                <BundleCard rec={rec} compact />
                <button className="btn primary" onClick={() => navigate(`/quote?session=${state!.session_id}`)}>Continue to quote</button>
              </div>
            )}
            {state?.stage === "handoff" && (
              <div className="banner info">A local Accel Business partner will call you back. Reference: {state.handoff_id}</div>
            )}
            <div ref={bottomRef} />
          </div>
          <form className="composer" onSubmit={(e) => { e.preventDefault(); send(input); }}>
            <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Type in English, हिंदी or Hinglish…"
              disabled={busy || !state} autoFocus />
            <button type="submit" className="btn primary" disabled={busy || !input.trim()}>Send</button>
          </form>
        </>
      )}
    </div>
  );
}
