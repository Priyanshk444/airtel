import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, inr, Order, QuoteLine, QuoteResponse } from "../api";

export default function Checkout() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const sessionId = params.get("session") ?? sessionStorage.getItem("udyam_session");
  const [lines, setLines] = useState<QuoteLine[]>([]);
  const [quote, setQuote] = useState<QuoteResponse | null>(null);
  const [form, setForm] = useState({ business_name: "", contact_name: "", phone: "", method: "upi", reference: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [order, setOrder] = useState<Order | null>(null);

  useEffect(() => {
    if (!sessionId) return;
    const saved = sessionStorage.getItem(`udyam_lines_${sessionId}`);
    const selected: QuoteLine[] = saved
      ? JSON.parse(saved).filter((l: { enabled: boolean }) => l.enabled).map((l: { product_id: string; quantity: number }) => ({ product_id: l.product_id, quantity: l.quantity }))
      : [];
    setLines(selected);
    api.getSession(sessionId).then((s) => {
      const p = s.profile as Record<string, string | undefined>;
      setForm((f) => ({ ...f, business_name: p.business_name ?? "", contact_name: p.contact_name ?? "", phone: p.contact_phone ?? "" }));
      const useLines = selected.length ? selected : (s.recommendation?.items ?? []).map((i) => ({ product_id: i.product_id, quantity: i.quantity }));
      setLines(useLines);
      return api.quote({ session_id: sessionId, lines: useLines });
    }).then(setQuote).catch((e) => setError(String(e)));
  }, [sessionId]);

  async function pay(e: React.FormEvent) {
    e.preventDefault();
    if (!sessionId) return;
    setBusy(true);
    setError(null);
    try {
      const o = await api.placeOrder({
        session_id: sessionId, lines,
        customer: { business_name: form.business_name, contact_name: form.contact_name || null, phone: form.phone || null },
        payment: { method: form.method, reference: form.reference || null },
      });
      setOrder(o);
      sessionStorage.setItem("udyam_order", o.id);
    } catch (err) {
      setError(String(err).replace(/^Error:\s*/, ""));
    } finally {
      setBusy(false);
    }
  }

  if (!sessionId) return <div className="page"><div className="card">Start with the advisor first.</div></div>;
  if (error && !quote) return <div className="page"><div className="banner error">{error}</div></div>;
  if (!quote) return <div className="page"><div className="card">Preparing checkout…</div></div>;

  if (order) {
    return (
      <div className="page">
        <div className="card success">
          <div className="check">✓</div>
          <h2>Order placed</h2>
          <p>Order <strong>{order.id}</strong> for {order.business_name}. {order.payment.message}</p>
          <p>Next: verify your business in about two minutes so we can book the technician. Expected activation <strong>{order.timeline[order.timeline.length - 1].expected_at}</strong>.</p>
          <button className="btn primary big" onClick={() => navigate(`/kyc?order=${order.id}`)}>Verify my business (KYC)</button>
          <button className="btn ghost" onClick={() => navigate(`/track?order=${order.id}`)}>Track this order</button>
        </div>
      </div>
    );
  }

  const p = quote.pricing;
  return (
    <div className="page">
      <div className="card">
        <h3>Order summary</h3>
        <ul className="plain summary">
          {quote.items.map((i) => (
            <li key={i.product_id}><span>{i.product_name} x{i.quantity}</span><span>{inr(i.monthly_inr)}</span></li>
          ))}
        </ul>
        <div className="totals">
          <div><span>Monthly (from activation)</span><strong>{inr(p.monthly_total_inr)}</strong></div>
          <div><span>Pay today (setup)</span><strong>{inr(p.setup_total_inr)}</strong></div>
          <div><span>Plan</span><strong>{p.contract_months} months</strong></div>
        </div>
      </div>

      <form className="card form" onSubmit={pay}>
        <h3>Business and payment</h3>
        <label>Business name<input required value={form.business_name} onChange={(e) => setForm({ ...form, business_name: e.target.value })} /></label>
        <label>Contact name<input value={form.contact_name} onChange={(e) => setForm({ ...form, contact_name: e.target.value })} /></label>
        <label>Mobile number<input inputMode="numeric" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="10-digit number" /></label>
        <div className="seg">
          {[["upi", "UPI"], ["card", "Card"], ["netbanking", "Net banking"], ["pay_later", "Add to first bill"]].map(([v, l]) => (
            <button type="button" key={v} className={form.method === v ? "on" : ""} onClick={() => setForm({ ...form, method: v })}>{l}</button>
          ))}
        </div>
        {form.method !== "pay_later" && (
          <label>{form.method === "upi" ? "UPI ID" : form.method === "card" ? "Card number (mock)" : "Bank"}
            <input value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} placeholder={form.method === "upi" ? "name@bank" : "demo only, nothing is charged"} />
          </label>
        )}
        <p className="muted small">Mock payment for the prototype. Nothing is charged. Type FAIL in the field to see a declined payment.</p>
        {error && <div className="banner error">{error}</div>}
        <button className="btn primary big" disabled={busy || quote.items.length === 0}>
          {busy ? "Processing…" : form.method === "pay_later" ? "Place order" : `Pay ${inr(p.setup_total_inr)} and place order`}
        </button>
        <button type="button" className="btn ghost" onClick={() => navigate(`/quote?session=${sessionId}`)}>Back to quote</button>
      </form>
    </div>
  );
}
