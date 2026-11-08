import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AdvisorState, api, inr, QuoteLine, QuoteResponse, Recommendation } from "../api";

interface Line {
  product_id: string;
  name: string;
  unit: string;
  description?: string;
  quantity: number;
  unit_price: number;
  setup_unit: number;
  locked: boolean;      // core items from the advisor cannot be switched off
  enabled: boolean;
  why: string;
}

function linesFromRecommendation(rec: Recommendation): Line[] {
  const items: Line[] = rec.items.map((i) => ({
    product_id: i.product_id, name: i.product_name, unit: i.unit, quantity: i.quantity,
    unit_price: i.unit_price_inr, setup_unit: i.quantity ? i.setup_inr / i.quantity : 0,
    locked: i.is_core, enabled: true, why: i.reasons[0]?.message ?? "",
  }));
  const addons: Line[] = rec.add_ons.map((a) => ({
    product_id: a.product_id, name: a.product_name, unit: a.unit, description: a.description, quantity: a.default_quantity,
    unit_price: a.unit_price_inr, setup_unit: a.default_quantity ? a.setup_inr / a.default_quantity : 0,
    locked: false, enabled: false, why: a.description,
  }));
  return [...items, ...addons];
}

export default function Quote() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const sessionId = params.get("session") ?? sessionStorage.getItem("udyam_session");
  const [session, setSession] = useState<AdvisorState | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [quote, setQuote] = useState<QuoteResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (!sessionId) return;
    api.getSession(sessionId).then((s) => {
      setSession(s);
      if (s.recommendation) {
        const saved = sessionStorage.getItem(`udyam_lines_${sessionId}`);
        setLines(saved ? JSON.parse(saved) : linesFromRecommendation(s.recommendation));
      }
    }).catch((e) => setError(String(e)));
  }, [sessionId]);

  const selected: QuoteLine[] = useMemo(
    () => lines.filter((l) => l.enabled && l.quantity > 0).map((l) => ({ product_id: l.product_id, quantity: l.quantity })),
    [lines]
  );

  // reprice on the server, debounced, so the total is always the engine's number
  useEffect(() => {
    if (!sessionId || lines.length === 0) return;
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      api.quote({ session_id: sessionId, lines: selected }).then(setQuote).catch((e) => setError(String(e)));
      sessionStorage.setItem(`udyam_lines_${sessionId}`, JSON.stringify(lines));
    }, 150);
  }, [selected, lines, sessionId]);

  function update(pid: string, patch: Partial<Line>) {
    setLines((ls) => ls.map((l) => (l.product_id === pid ? { ...l, ...patch } : l)));
  }

  if (!sessionId) {
    return (
      <div className="page"><div className="card"><h2>No quote yet</h2><p>Talk to the advisor first so we know your business.</p>
        <button className="btn primary" onClick={() => navigate("/advisor")}>Open the advisor</button></div></div>
    );
  }
  if (error) return <div className="page"><div className="banner error">{error}</div></div>;
  if (!session) return <div className="page"><div className="card">Loading your quote…</div></div>;
  if (!session.recommendation) {
    return (
      <div className="page"><div className="card"><h2>Almost there</h2><p>The advisor has not recommended a bundle yet. Finish the chat and come back.</p>
        <button className="btn primary" onClick={() => navigate("/advisor")}>Back to the advisor</button></div></div>
    );
  }

  const rec = session.recommendation;
  const p = quote?.pricing ?? rec.pricing;
  const blocked = (quote?.issues ?? []).filter((i) => i.severity === "blocking");
  const included = lines.filter((l) => !l.description);
  const addons = lines.filter((l) => l.description);

  return (
    <div className="page quote">
      <div className="card price-head sticky">
        <small>Your monthly price</small>
        <div className="price">{inr(p.monthly_total_inr)} <span>/ month</span></div>
        <div className="price-meta">
          <span>One-time setup <strong>{inr(p.setup_total_inr)}</strong></span>
          <span>Plan <strong>{p.contract_months} months</strong></span>
          <span>Live in <strong>~{p.expected_install_days} days</strong></span>
        </div>
      </div>

      <section className="card">
        <h3>Your bundle</h3>
        <ul className="toggle-list">
          {included.map((l) => <LineRow key={l.product_id} line={l} onChange={update} />)}
        </ul>
      </section>

      {addons.length > 0 && (
        <section className="card">
          <h3>Add-ons</h3>
          <p className="muted">Switch on anything you want. The price above updates instantly.</p>
          <ul className="toggle-list">
            {addons.map((l) => <LineRow key={l.product_id} line={l} onChange={update} />)}
          </ul>
        </section>
      )}

      {rec.excluded.length > 0 && (
        <section className="card muted-card">
          <h3>Not available for you</h3>
          <ul className="plain">
            {rec.excluded.map((e) => (
              <li key={e.product_id}><strong>{e.product_name}</strong> - {e.reasons[0]?.message}{e.alternative_product_name && <> We offered {e.alternative_product_name} instead.</>}</li>
            ))}
          </ul>
        </section>
      )}

      {blocked.length > 0 && (
        <div className="banner error">{blocked.map((b) => <p key={b.product_id}>{b.message}</p>)}</div>
      )}

      <div className="card fineprint-card">
        <p>Prices are per month before GST. Setup is charged once. The plan length is the longest minimum term among your items. No hidden charges, one bill, one support number.</p>
      </div>

      <button className="btn primary big" disabled={!quote || quote.items.length === 0}
        onClick={() => navigate(`/checkout?session=${sessionId}`)}>
        Proceed to checkout
      </button>
      <button className="btn ghost" onClick={() => navigate("/advisor")}>Change something with the advisor</button>
    </div>
  );
}

function LineRow({ line, onChange }: { line: Line; onChange: (pid: string, patch: Partial<Line>) => void }) {
  const perUnit = !["per account", "per pack", "per number", "per IP"].includes(line.unit);
  return (
    <li className={line.enabled ? "" : "off"}>
      <div className="toggle-row">
        <div className="toggle-text">
          <strong>{line.name}</strong>
          <small>{line.why}</small>
          <small className="unit">{inr(line.unit_price)} {line.unit}{line.setup_unit ? ` · setup ${inr(line.setup_unit)} ${line.unit}` : ""}</small>
        </div>
        <div className="toggle-right">
          <span className="amt">{line.enabled ? inr(line.unit_price * line.quantity) : "-"}</span>
          {line.locked ? (
            <span className="tag">included</span>
          ) : (
            <label className="switch">
              <input type="checkbox" checked={line.enabled} onChange={(e) => onChange(line.product_id, { enabled: e.target.checked })} />
              <span />
            </label>
          )}
        </div>
      </div>
      {line.enabled && perUnit && (
        <div className="stepper">
          <button type="button" onClick={() => onChange(line.product_id, { quantity: Math.max(1, line.quantity - 1) })}>-</button>
          <span>{line.quantity} {line.unit.replace("per ", "")}{line.quantity > 1 ? "s" : ""}</span>
          <button type="button" onClick={() => onChange(line.product_id, { quantity: Math.min(200, line.quantity + 1) })}>+</button>
        </div>
      )}
    </li>
  );
}
