import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, inr, Order, TimelineStep } from "../api";

const NEXT_STEP: Record<string, string> = {
  ordered: "Finish the quick KYC so we can book a technician. Nothing else is needed from you.",
  kyc_verified: "Your documents are verified. We are assigning a technician in your area.",
  technician_assigned: "A technician has your order. You will get a call to agree an installation slot.",
  installation_scheduled: "Installation is booked. Please keep the site open and someone available with the setup location.",
  activated: "Your services are live. Your first bill arrives at the start of next month.",
};

export default function Track() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const orderParam = params.get("order") ?? sessionStorage.getItem("udyam_order");
  const sessionId = sessionStorage.getItem("udyam_session");
  const [order, setOrder] = useState<Order | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [lookup, setLookup] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (orderParam) {
      api.getOrder(orderParam).then(setOrder).catch((e) => setError(String(e)));
    } else {
      // no order in hand: show this session's orders, else the demo orders
      api.listOrders(sessionId ?? undefined).then((list) => (list.length ? setOrders(list) : api.listOrders().then(setOrders))).catch(() => undefined);
    }
  }, [orderParam, sessionId]);

  async function advance() {
    if (!order) return;
    setBusy(true);
    try {
      setOrder(await api.advance(order.id));
    } finally {
      setBusy(false);
    }
  }

  if (!orderParam) {
    return (
      <div className="page">
        <div className="card">
          <h2>Track an order</h2>
          <form className="lookup" onSubmit={(e) => { e.preventDefault(); if (lookup.trim()) navigate(`/track?order=${lookup.trim()}`); }}>
            <input className="text" value={lookup} onChange={(e) => setLookup(e.target.value)} placeholder="Order number, e.g. ord_…" />
            <button className="btn primary">Track</button>
          </form>
        </div>
        {orders.length > 0 && (
          <div className="card">
            <h3>{sessionId && orders[0].session_id === sessionId ? "Your orders" : "Demo orders"}</h3>
            <ul className="plain orders">
              {orders.map((o) => (
                <li key={o.id} onClick={() => navigate(`/track?order=${o.id}`)}>
                  <div><strong>{o.business_name}</strong><small className="muted">{o.city} · {o.id}</small></div>
                  <span className={`status-pill ${o.current_status}`}>{o.timeline.find((s) => s.status === o.current_status)?.label}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  }
  if (error) return <div className="page"><div className="banner error">{error}</div></div>;
  if (!order) return <div className="page"><div className="card">Loading order…</div></div>;

  const currentIdx = order.timeline.findIndex((s) => s.status === order.current_status);
  const activation = order.timeline[order.timeline.length - 1];
  const done = order.current_status === "activated";

  return (
    <div className="page">
      <div className={`card track-head ${done ? "done" : ""}`}>
        <small className="muted">Order {order.id} · {order.business_name}</small>
        <h2>{done ? "You are live" : `Expected activation ${fmt(activation.expected_at)}`}</h2>
        <p className="muted">{NEXT_STEP[order.current_status]}</p>
      </div>

      <div className="card">
        <ol className="timeline">
          {order.timeline.map((s, i) => (
            <TimelineRow key={s.status} step={s} state={i < currentIdx ? "done" : i === currentIdx ? "current" : "todo"} />
          ))}
        </ol>
      </div>

      {order.current_status === "ordered" && (
        <button className="btn primary big" onClick={() => navigate(`/kyc?order=${order.id}`)}>Verify my business now</button>
      )}

      <div className="card">
        <h3>Your plan</h3>
        <ul className="plain summary">
          {order.items.map((i) => <li key={i.product_id}><span>{i.product_name} x{i.quantity}</span><span>{inr(i.monthly_inr)}</span></li>)}
        </ul>
        <div className="totals">
          <div><span>Monthly from activation</span><strong>{inr(order.pricing.monthly_total_inr)}</strong></div>
          <div><span>Setup {order.payment.status === "paid" ? "paid" : order.payment.status}</span><strong>{inr(order.pricing.setup_total_inr)}</strong></div>
          <div><span>Plan</span><strong>{order.pricing.contract_months} months</strong></div>
        </div>
      </div>

      <div className="card muted-card">
        <h3>No need to call</h3>
        <p className="small muted">This page updates at every step, and you get a WhatsApp/SMS message if you allowed service updates. If a date slips, the new date shows here first.</p>
        {!done && (
          <button className="btn ghost" disabled={busy} onClick={advance}>
            {busy ? "…" : "Demo: simulate next step"}
          </button>
        )}
      </div>
      <button className="btn ghost" onClick={() => navigate("/track")}>All orders</button>
    </div>
  );
}

function TimelineRow({ step, state }: { step: TimelineStep; state: "done" | "current" | "todo" }) {
  return (
    <li className={`tl ${state}`}>
      <span className="tl-dot" />
      <div className="tl-body">
        <strong>{step.label}</strong>
        <small className="muted">
          {step.done_at ? `Done ${fmt(step.done_at.slice(0, 10))}` : `Expected ${fmt(step.expected_at)}`}
        </small>
      </div>
    </li>
  );
}

function fmt(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}
