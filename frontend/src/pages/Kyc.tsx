import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, ConsentPurpose, KycCase, Specimen } from "../api";

const DOC_LABELS: Record<string, string> = {
  gst_certificate: "GST registration certificate",
  udyam_certificate: "Udyam registration certificate",
  signatory_id: "Authorised signatory ID",
  address_proof: "Address proof (electricity bill, last 90 days)",
};
const STATUS_LABEL: Record<string, string> = { pass: "Pass", fail: "Fail", review: "Needs review", not_applicable: "n/a" };

type Step = "consent" | "upload" | "result";

export default function Kyc() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const sessionId = params.get("session") ?? sessionStorage.getItem("udyam_session");
  const orderId = params.get("order") ?? sessionStorage.getItem("udyam_order");
  const [step, setStep] = useState<Step>("consent");
  const [purposes, setPurposes] = useState<ConsentPurpose[]>([]);
  const [ticks, setTicks] = useState<Record<string, boolean>>({ verification: false });
  const [kase, setKase] = useState<KycCase | null>(null);
  const [specimens, setSpecimens] = useState<Specimen[]>([]);
  const [sample, setSample] = useState("K12");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.consentPurposes().then(setPurposes).catch((e) => setError(String(e)));
    api.specimens().then(setSpecimens).catch(() => undefined);
  }, []);

  async function agree() {
    if (!sessionId) return;
    setBusy("consent");
    setError(null);
    try {
      await api.giveConsent(sessionId, ticks);
      const c = await api.newCase(sessionId, orderId);
      setKase(c);
      setStep("upload");
    } catch (e) {
      setError(String(e).replace(/^Error:\s*/, ""));
    } finally {
      setBusy(null);
    }
  }

  async function uploadFile(docType: string, file: File) {
    if (!kase) return;
    setBusy(docType);
    setError(null);
    try {
      const c = await api.uploadDocument(kase.id, docType, file);
      setKase(c);
    } catch (e) {
      setError(String(e).replace(/^Error:\s*/, ""));
    } finally {
      setBusy(null);
    }
  }

  async function useSample(docType: string) {
    if (!kase) return;
    setBusy(docType);
    setError(null);
    try {
      const c = await api.uploadSpecimen(kase.id, sample, docType);
      setKase(c);
    } catch (e) {
      setError(String(e).replace(/^Error:\s*/, ""));
    } finally {
      setBusy(null);
    }
  }

  if (!sessionId) return <div className="page"><div className="card">Start with the advisor first so we know which path (GST or Udyam) applies to you.</div></div>;

  // ---------------------------------------------------------------- consent
  if (step === "consent") {
    return (
      <div className="page">
        <div className="card">
          <h2>Before we look at any document</h2>
          <p className="muted">
            Under the Digital Personal Data Protection Act, 2023 we ask your permission for each purpose separately. Only the first one is needed to
            activate your connection. You can withdraw the others any time from the app.
          </p>
        </div>
        {purposes.map((p) => (
          <label key={p.key} className={`card consent ${p.required ? "required" : ""}`}>
            <div className="consent-head">
              <input type="checkbox" checked={!!ticks[p.key]} onChange={(e) => setTicks({ ...ticks, [p.key]: e.target.checked })} />
              <strong>{p.title}</strong>
              {p.required && <span className="tag">required</span>}
            </div>
            <dl>
              <dt>What we collect</dt><dd>{p.what}</dd>
              <dt>Why</dt><dd>{p.why}</dd>
              <dt>How long we keep it</dt><dd>{p.retention}</dd>
            </dl>
          </label>
        ))}
        {error && <div className="banner error">{error}</div>}
        <button className="btn primary big" disabled={!ticks.verification || busy === "consent"} onClick={agree}>
          {ticks.verification ? "I agree, continue to documents" : "Tick the required consent to continue"}
        </button>
        <p className="fineprint">Document images are read once and deleted. We keep only the extracted details, masked, for 90 days.</p>
      </div>
    );
  }

  if (!kase) return <div className="page"><div className="card">Preparing…</div></div>;
  const required = kase.required_documents;
  const optional = Object.keys(DOC_LABELS).filter((d) => !required.includes(d));
  const done = required.every((d) => kase.documents[d]);

  // ----------------------------------------------------------------- upload
  if (step === "upload") {
    return (
      <div className="page">
        <div className="card">
          <h2>Upload your documents</h2>
          <p className="muted">
            Path: <strong>{kase.path === "gstin" ? "GST registered business" : kase.path === "udyam_only" ? "Udyam registered (no GST)" : "Alternative documents"}</strong>.
            Take a clear photo or choose a file. We read it instantly and check it against the GST and Udyam registries.
          </p>
          <div className="sample-row">
            <span className="muted small">Demo: use a sample applicant</span>
            <select value={sample} onChange={(e) => setSample(e.target.value)}>
              {specimens.map((s) => <option key={s.applicant} value={s.applicant}>{s.applicant} - {s.business_name}</option>)}
            </select>
          </div>
        </div>
        {[...required, ...optional].map((docType) => {
          const doc = kase.documents[docType];
          const isReq = required.includes(docType);
          return (
            <div key={docType} className={`card doc ${doc ? "done" : ""}`}>
              <div className="doc-head">
                <strong>{DOC_LABELS[docType]}</strong>
                <span className="tag">{isReq ? "required" : "optional"}</span>
              </div>
              {doc ? (
                <ul className="plain small fields">
                  {Object.entries(doc).filter(([k]) => !["legibility", "confidence", "notes"].includes(k)).map(([k, v]) => (
                    <li key={k}><span className="muted">{k.replace(/_/g, " ")}</span><span>{String(v ?? "-")}</span></li>
                  ))}
                  {typeof doc.legibility === "string" && doc.legibility !== "clear" && (
                    <li><span className="muted">image</span><span className="warn">{doc.legibility}</span></li>
                  )}
                </ul>
              ) : (
                <div className="doc-actions">
                  <label className="btn">
                    {busy === docType ? "Reading…" : "Photo / file"}
                    <input type="file" accept="image/*" capture="environment" hidden disabled={!!busy}
                      onChange={(e) => e.target.files?.[0] && uploadFile(docType, e.target.files[0])} />
                  </label>
                  <button className="btn ghost" disabled={!!busy} onClick={() => useSample(docType)}>
                    {busy === docType ? "Reading…" : `Use sample ${sample}`}
                  </button>
                </div>
              )}
            </div>
          );
        })}
        {error && <div className="banner error">{error}</div>}
        <button className="btn primary big" disabled={!done} onClick={() => setStep("result")}>
          {done ? "See verification result" : `Upload the ${required.filter((d) => !kase.documents[d]).length} required document(s)`}
        </button>
      </div>
    );
  }

  // ----------------------------------------------------------------- result
  const checks = kase.checks.checks ?? [];
  const status = kase.status;
  return (
    <div className="page">
      <div className={`card verdict ${status}`}>
        <h2>{status === "verified" ? "Verified" : status === "needs_review" ? "Almost there" : "We could not verify this yet"}</h2>
        <p>{kase.checks.summary}</p>
        <small className="muted">Case {kase.id} · details kept until {kase.retention_until}</small>
      </div>
      <div className="card">
        <h3>Checks</h3>
        <ul className="plain checks">
          {checks.map((c) => (
            <li key={c.code} className={c.status}>
              <div className="check-head"><span className="dot" /><strong>{c.title}</strong><span className="tag">{STATUS_LABEL[c.status]}</span></div>
              <p className="muted small">{c.reason}</p>
            </li>
          ))}
        </ul>
      </div>
      {status === "verified" && orderId && (
        <button className="btn primary big" onClick={() => navigate(`/track?order=${orderId}`)}>Track my installation</button>
      )}
      {status !== "verified" && (
        <>
          <button className="btn primary big" onClick={() => setStep("upload")}>Fix and re-upload</button>
          <p className="muted small">If you have no GSTIN, you can continue with your Udyam number or other documents; a local partner completes the verification.</p>
        </>
      )}
      <button className="btn ghost" onClick={() => navigate("/")}>Home</button>
    </div>
  );
}
