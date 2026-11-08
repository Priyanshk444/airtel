import { inr, Recommendation } from "../api";

export default function BundleCard({ rec, compact = false }: { rec: Recommendation; compact?: boolean }) {
  const p = rec.pricing;
  return (
    <div className="card bundle">
      <div className="bundle-head">
        <div>
          <small>Recommended for a {rec.segment_label.toLowerCase()} business</small>
          <div className="price">
            {inr(p.monthly_total_inr)} <span>/ month</span>
          </div>
          <small>
            Setup {inr(p.setup_total_inr)} · {p.contract_months}-month plan · live in about {p.expected_install_days} days
          </small>
        </div>
      </div>
      <ul className="items">
        {rec.items.map((i) => (
          <li key={i.product_id}>
            <div className="item-main">
              <strong>{i.product_name}</strong>
              <span className="qty">x{i.quantity}</span>
              <span className="amt">{inr(i.monthly_inr)}</span>
            </div>
            {!compact && <p className="why">{i.reasons[0]?.message}</p>}
            {!i.is_core && <span className="tag">optional</span>}
          </li>
        ))}
      </ul>
      {rec.excluded.length > 0 && !compact && (
        <div className="excluded">
          <strong>Not included</strong>
          <ul>
            {rec.excluded.map((e) => (
              <li key={e.product_id}>
                {e.product_name}: {e.reasons[0]?.message}
                {e.alternative_product_name && <> Offered instead: {e.alternative_product_name}.</>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {rec.warnings.length > 0 && (
        <div className="warnings">
          {rec.warnings.map((w, i) => (
            <p key={i}>{w}</p>
          ))}
        </div>
      )}
    </div>
  );
}
