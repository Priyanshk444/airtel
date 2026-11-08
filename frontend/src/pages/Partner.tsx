import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, HandoffLead, inr, PartnerSession, PropensityLead, PropensityModel } from "../api";

type Tab = "handoffs" | "call" | "assisted";
const PARTNER_KEY = "udyam_partner";

export default function Partner() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("handoffs");
  const [territories, setTerritories] = useState<Record<string, string[]>>({});
  const [state, setState] = useState(sessionStorage.getItem("udyam_partner_state") ?? "");
  const [city, setCity] = useState("");
  const [partner, setPartner] = useState(sessionStorage.getItem(PARTNER_KEY) ?? "partner_demo_01");
  const [handoffs, setHandoffs] = useState<HandoffLead[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [leads, setLeads] = useState<PropensityLead[]>([]);
  const [model, setModel] = useState<PropensityModel | null>(null);
  const [sessions, setSessions] = useState<PartnerSession[]>([]);

  useEffect(() => { api.territories().then(setTerritories).catch(() => undefined); }, []);
  useEffect(() => {
    sessionStorage.setItem("udyam_partner_state", state);
    sessionStorage.setItem(PARTNER_KEY, partner);
    if (tab === "handoffs") api.handoffs({ state: state || undefined, city: city || undefined }).then(setHandoffs).catch(() => undefined);
    if (tab === "call") {
      api.propensityLeads({ state: state || undefined, city: city || undefined, limit: 25 }).then(setLeads).catch(() => undefined);
      if (!model) api.propensityModel().then(setModel).catch(() => undefined);
    }
    if (tab === "assisted") api.partnerSessions(partner).then(setSessions).catch(() => undefined);
  }, [tab, state, city, partner]); // eslint-disable-line react-hooks/exhaustive-deps

  async function setStatus(id: string, status: string) {
    const updated = await api.updateHandoff(id, status);
    setHandoffs((hs) => hs.map((h) => (h.id === id ? updated : h)));
  }

  function startAssisted() {
    sessionStorage.removeItem("udyam_session");
    navigate(`/advisor?partner=${encodeURIComponent(partner)}`);
  }

  return (
    <div className="page partner">
      <div className="card filters">
        <div className="filter-row">
          <label>Territory
            <select value={state} onChange={(e) => { setState(e.target.value); setCity(""); }}>
              <option value="">All states</option>
              {Object.keys(territories).map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label>City
            <select value={city} onChange={(e) => setCity(e.target.value)} disabled={!state}>
              <option value="">All</option>
              {(territories[state] ?? []).map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
        </div>
        <div className="seg tabs">
          <button className={tab === "handoffs" ? "on" : ""} onClick={() => setTab("handoffs")}>Handoffs</button>
          <button className={tab === "call" ? "on" : ""} onClick={() => setTab("call")}>Who to call</button>
          <button className={tab === "assisted" ? "on" : ""} onClick={() => setTab("assisted")}>Assisted</button>
        </div>
      </div>

      {tab === "handoffs" && (
        <>
          <p className="muted small">Leads the digital advisor could not close, with the conversation summary. Newest first.</p>
          {handoffs.length === 0 && <div className="card muted">No handoff leads for this territory.</div>}
          {handoffs.map((h) => (
            <div key={h.id} className={`card lead ${h.status}`}>
              <div className="lead-head" onClick={() => setOpen(open === h.id ? null : h.id)}>
                <div>
                  <strong>{String(h.contact ?? h.profile?.business_name ?? "Unknown business")}</strong>
                  <small className="muted">{h.city}{h.state ? `, ${h.state}` : ""} · {h.segment ?? "segment unknown"} · {new Date(h.created_at).toLocaleDateString("en-IN")}</small>
                </div>
                <span className={`status-pill ${h.status}`}>{h.status}</span>
              </div>
              <p className="reason"><span className="tag">{h.reason.replace(/_/g, " ")}</span></p>
              <p className="small">{h.summary}</p>
              {open === h.id && (
                <div className="lead-detail">
                  {h.recommendation && <p className="small"><strong>Quoted:</strong> {inr(h.recommendation.pricing.monthly_total_inr)}/month · {h.recommendation.items.map((i) => `${i.product_name} x${i.quantity}`).join(", ")}</p>}
                  {h.transcript.length > 0 && (
                    <div className="transcript">
                      {h.transcript.map((t, i) => <p key={i} className={t.role}><b>{t.role === "user" ? "Customer" : "Advisor"}:</b> {t.text}</p>)}
                    </div>
                  )}
                </div>
              )}
              <div className="lead-actions">
                {h.status === "open" && <button className="btn" onClick={() => setStatus(h.id, "contacted")}>Mark contacted</button>}
                {h.status !== "closed" && <button className="btn ghost" onClick={() => setStatus(h.id, "closed")}>Close</button>}
                {h.status === "closed" && <button className="btn ghost" onClick={() => setStatus(h.id, "open")}>Reopen</button>}
              </div>
            </div>
          ))}
        </>
      )}

      {tab === "call" && (
        <>
          {model && (
            <div className="card model">
              <h3>How this ranking works</h3>
              <p className="small muted">
                Logistic regression on last quarter's leads, using only facts known when the lead came in. On a held-out 20% ({model.metrics.test_leads} leads):
                AUC <strong>{model.metrics.roc_auc}</strong>, calling the top 10% finds activations at <strong>{model.metrics.lift_top10pct}x</strong> the base rate
                ({Math.round(model.metrics.precision_top10pct * 100)}% vs {Math.round(model.metrics.activation_rate_baseline * 100)}%).
              </p>
              <details>
                <summary className="small">Top factors</summary>
                <ul className="plain small factors">
                  {model.top_factors.map((f) => <li key={f.factor}><span>{f.factor}</span><span className={f.direction}>{f.direction} {Math.abs(f.weight).toFixed(2)}</span></li>)}
                </ul>
              </details>
            </div>
          )}
          {leads.map((l, i) => (
            <div key={l.lead_id} className="card lead">
              <div className="lead-head">
                <div>
                  <strong>{i + 1}. {l.business_name}</strong>
                  <small className="muted">{l.business_type} · {l.city} · {l.lead_source} · {l.preferred_language} · {l.has_gstin ? "GSTIN" : "no GSTIN"} · stage: {l.stage_reached}</small>
                </div>
                <span className="score">{Math.round(l.score * 100)}%</span>
              </div>
              <p className="small muted">{l.reasons.join(" · ")} · contact {l.contact_name}</p>
            </div>
          ))}
        </>
      )}

      {tab === "assisted" && (
        <>
          <div className="card">
            <h3>Assisted mode</h3>
            <p className="small muted">Fill the journey on a shop owner's behalf, on your phone, in their language. The owner still gives KYC consent on the screen themselves.</p>
            <label className="small muted">Your partner ID<input className="text" value={partner} onChange={(e) => setPartner(e.target.value)} /></label>
            <button className="btn primary big" onClick={startAssisted}>Start a new customer</button>
          </div>
          {sessions.map((s) => (
            <div key={s.id} className="card lead">
              <div className="lead-head">
                <div>
                  <strong>{String(s.profile?.business_name ?? s.profile?.business_type ?? "New customer")}</strong>
                  <small className="muted">{String(s.profile?.city ?? "")} · {s.segment_label ?? s.stage} · {new Date(s.updated_at).toLocaleString("en-IN")}</small>
                </div>
                <span className="score">{s.monthly_total_inr ? inr(s.monthly_total_inr) : s.stage}</span>
              </div>
              <div className="lead-actions">
                <button className="btn" onClick={() => { sessionStorage.setItem("udyam_session", s.id); navigate(`/quote?session=${s.id}`); }}>Open quote</button>
                {s.order && <button className="btn ghost" onClick={() => navigate(`/track?order=${s.order!.id}`)}>Order: {s.order.current_status.replace(/_/g, " ")}</button>}
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
