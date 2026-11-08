// Tap-to-answer advisor: no LLM. Collects the same profile with buttons and asks the rule engine.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AdvisorState, api } from "../api";
import BundleCard from "./BundleCard";

type Lang = "en" | "hi";
const T = {
  en: {
    business: "What kind of business do you run?", city: "Which city?", otherCity: "Other city", tier: "Is it a big metro?",
    metro: "Big metro", smaller: "Smaller city", staff: "How many people work there (including you)?", sites: "How many shops or branches?",
    gst: "Do you have a GST registration?", needs: "What do you need? Tap all that apply.", fibreNo: "Fibre cable does not reach my building",
    budget: "Monthly budget (optional)", noBudget: "Not sure", show: "Show my bundle", change: "Change answers", quote: "Continue to quote",
    human: "Talk to a person", callback: "Best time or number to call (optional)", send: "Request a call back", typeOther: "Type your business",
    lines: "Mobile lines", cameras: "Cameras", vehicles: "Vehicles", machines: "Machines",
    gstOpts: ["Yes, active", "Yes, but cancelled or suspended", "No, but I have Udyam", "Neither"],
  },
  hi: {
    business: "आपका कौन सा व्यवसाय है?", city: "कौन सा शहर?", otherCity: "दूसरा शहर", tier: "क्या यह बड़ा महानगर है?",
    metro: "बड़ा महानगर", smaller: "छोटा शहर", staff: "कितने लोग काम करते हैं (आप समेत)?", sites: "कितनी दुकानें या शाखाएँ?",
    gst: "क्या आपके पास GST रजिस्ट्रेशन है?", needs: "आपको क्या चाहिए? सब चुनें।", fibreNo: "मेरी बिल्डिंग तक फाइबर नहीं पहुँचता",
    budget: "मासिक बजट (वैकल्पिक)", noBudget: "पता नहीं", show: "मेरा बंडल दिखाइए", change: "जवाब बदलें", quote: "कोटेशन देखें",
    human: "किसी व्यक्ति से बात करें", callback: "कॉल का सही समय या नंबर (वैकल्पिक)", send: "कॉल बैक माँगें", typeOther: "अपना व्यवसाय लिखें",
    lines: "मोबाइल लाइनें", cameras: "कैमरे", vehicles: "गाड़ियाँ", machines: "मशीनें",
    gstOpts: ["हाँ, चालू है", "हाँ, पर रद्द/निलंबित है", "नहीं, पर Udyam है", "दोनों नहीं"],
  },
};

const BUSINESSES: { value: string; en: string; hi: string }[] = [
  { value: "Kirana store", en: "Kirana / general store", hi: "किराना दुकान" },
  { value: "Salon", en: "Salon", hi: "सैलून" },
  { value: "Pharmacy", en: "Pharmacy", hi: "दवा की दुकान" },
  { value: "Restaurant", en: "Restaurant / cafe", hi: "रेस्टोरेंट / कैफ़े" },
  { value: "Boutique", en: "Shop / boutique", hi: "दुकान / बुटीक" },
  { value: "Clinic", en: "Clinic / lab", hi: "क्लिनिक / लैब" },
  { value: "CA firm", en: "CA / law / office", hi: "CA / वकील / ऑफ़िस" },
  { value: "Coaching centre", en: "Coaching centre", hi: "कोचिंग सेंटर" },
  { value: "Retail chain", en: "Chain of stores", hi: "कई दुकानें (चेन)" },
  { value: "Manufacturing unit", en: "Factory / workshop", hi: "फैक्ट्री / वर्कशॉप" },
];
const CITIES = ["Delhi", "Mumbai", "Bengaluru", "Hyderabad", "Chennai", "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Lucknow", "Indore",
  "Bhopal", "Patna", "Nagpur", "Nashik", "Surat", "Vadodara", "Ludhiana", "Kochi", "Coimbatore", "Mysuru", "Visakhapatnam"];
const NEEDS: { value: string; en: string; hi: string; count?: "num_mobile_lines" | "num_cameras" | "num_vehicles" | "num_machines" }[] = [
  { value: "internet", en: "Internet", hi: "इंटरनेट" },
  { value: "mobile_lines", en: "Business mobile lines", hi: "बिज़नेस मोबाइल लाइन", count: "num_mobile_lines" },
  { value: "whatsapp", en: "WhatsApp for customers", hi: "ग्राहकों के लिए WhatsApp" },
  { value: "pos_billing", en: "Billing + UPI/card", hi: "बिलिंग + UPI/कार्ड" },
  { value: "cctv", en: "CCTV on phone", hi: "फ़ोन पर CCTV", count: "num_cameras" },
  { value: "guest_wifi", en: "Wi-Fi for customers", hi: "ग्राहकों के लिए Wi-Fi" },
  { value: "email", en: "Business email", hi: "बिज़नेस ईमेल" },
  { value: "backup_internet", en: "Backup internet", hi: "बैकअप इंटरनेट" },
  { value: "cloud_telephony", en: "Phone system (IVR)", hi: "फ़ोन सिस्टम (IVR)" },
  { value: "sms", en: "Bulk SMS", hi: "बल्क SMS" },
  { value: "website", en: "Website", hi: "वेबसाइट" },
  { value: "toll_free", en: "Toll-free 1800 number", hi: "टोल-फ्री 1800 नंबर" },
  { value: "cloud_backup", en: "Data backup", hi: "डेटा बैकअप" },
  { value: "endpoint_security", en: "Antivirus", hi: "एंटीवायरस" },
  { value: "fast_internet", en: "Very fast 1 Gbps", hi: "बहुत तेज़ 1 Gbps" },
  { value: "dedicated_internet", en: "Leased line (SLA)", hi: "लीज़्ड लाइन (SLA)" },
  { value: "multi_site_management", en: "Manage all branches", hi: "सभी शाखाएँ एक जगह" },
  { value: "firewall", en: "Firewall", hi: "फ़ायरवॉल" },
  { value: "fleet_tracking", en: "Vehicle tracking", hi: "गाड़ी ट्रैकिंग", count: "num_vehicles" },
  { value: "machine_monitoring", en: "Machine monitoring", hi: "मशीन मॉनिटरिंग", count: "num_machines" },
];
const CORE = ["internet", "mobile_lines"];   // pre-selected; unticking means "I don't want it"
const BUDGETS = [0, 1500, 3000, 5000, 10000, 25000];

export default function GuidedAdvisor({ session, onState }: { session: AdvisorState; onState: (s: AdvisorState) => void }) {
  const navigate = useNavigate();
  const [lang, setLang] = useState<Lang>("en");
  const t = T[lang];
  const [business, setBusiness] = useState("");
  const [otherBusiness, setOtherBusiness] = useState("");
  const [city, setCity] = useState("");
  const [otherCity, setOtherCity] = useState("");
  const [tier, setTier] = useState<1 | 2 | null>(null);
  const [staff, setStaff] = useState(2);
  const [sites, setSites] = useState(1);
  const [gst, setGst] = useState<number | null>(null);
  const [needs, setNeeds] = useState<string[]>(CORE);
  const [counts, setCounts] = useState<Record<string, number>>({ num_mobile_lines: 1, num_cameras: 2, num_vehicles: 2, num_machines: 4 });
  const [noFibre, setNoFibre] = useState(false);
  const [budget, setBudget] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showHandoff, setShowHandoff] = useState(false);
  const [callback, setCallback] = useState("");

  const businessType = business === "other" ? otherBusiness.trim() : business;
  const cityName = city === "other" ? otherCity.trim() : city;
  const ready = !!businessType && !!cityName && (city !== "other" || tier !== null) && gst !== null;
  const rec = session.recommendation;

  const toggle = (v: string) => setNeeds((n) => (n.includes(v) ? n.filter((x) => x !== v) : [...n, v]));

  async function show() {
    setBusy(true);
    setError(null);
    const answers: Record<string, unknown> = {
      business_type: businessType, city: cityName, employee_count: staff, num_sites: sites,
      has_gstin: gst === 0 || gst === 1, gstin_status: gst === 1 ? "cancelled" : gst === 0 ? "active" : undefined,
      has_udyam: gst === 2, needs: needs, excluded_needs: CORE.filter((c) => !needs.includes(c)),
      fibre_feasible: noFibre ? false : undefined, monthly_budget_inr: budget || undefined,
      preferred_language: lang === "hi" ? "Hindi" : "English",
    };
    if (city === "other" && tier) answers.city_tier = tier;
    for (const n of NEEDS) if (n.count && needs.includes(n.value)) answers[n.count] = counts[n.count];
    const line = `${businessType}, ${cityName}, ${staff} staff, ${sites} site(s), ${T.en.gstOpts[gst ?? 3]}. Needs: ${needs.join(", ") || "none"}.`;
    try {
      onState(await api.guided(session.session_id, answers, line));
    } catch (e) {
      setError(String(e).replace(/^Error:\s*/, ""));
    } finally {
      setBusy(false);
    }
  }

  async function handoff() {
    setBusy(true);
    try {
      onState(await api.handoff(session.session_id, rec ? "customer_hesitant" : "wants_human", callback || null));
      setShowHandoff(false);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (rec && !busy && session.stage !== "collecting") {
    return (
      <div className="guided">
        <BundleCard rec={rec} />
        <button className="btn primary big" onClick={() => navigate(`/quote?session=${session.session_id}`)}>{t.quote}</button>
        <button className="btn ghost" onClick={() => onState({ ...session, recommendation: null, stage: "collecting" })}>{t.change}</button>
        {handoffBox()}
      </div>
    );
  }

  function handoffBox() {
    if (session.stage === "handoff") return <div className="banner info">A local Accel Business partner will call you back. Ref {session.handoff_id}</div>;
    if (!showHandoff) return <button className="btn ghost" onClick={() => setShowHandoff(true)}>{t.human}</button>;
    return (
      <div className="card form">
        <label>{t.callback}<input value={callback} onChange={(e) => setCallback(e.target.value)} placeholder="e.g. after 6 pm" /></label>
        <button className="btn primary" disabled={busy} onClick={handoff}>{t.send}</button>
      </div>
    );
  }

  return (
    <div className="guided">
      <div className="seg lang">
        <button className={lang === "en" ? "on" : ""} onClick={() => setLang("en")}>English</button>
        <button className={lang === "hi" ? "on" : ""} onClick={() => setLang("hi")}>हिंदी</button>
      </div>

      <Q title={t.business}>
        <div className="chips-grid">
          {BUSINESSES.map((b) => <Chip key={b.value} on={business === b.value} onClick={() => setBusiness(b.value)}>{b[lang]}</Chip>)}
          <Chip on={business === "other"} onClick={() => setBusiness("other")}>{lang === "hi" ? "अन्य" : "Other"}</Chip>
        </div>
        {business === "other" && <input className="text" value={otherBusiness} onChange={(e) => setOtherBusiness(e.target.value)} placeholder={t.typeOther} />}
      </Q>

      <Q title={t.city}>
        <select className="text" value={city} onChange={(e) => setCity(e.target.value)}>
          <option value="">-</option>
          {CITIES.map((c) => <option key={c} value={c}>{c}</option>)}
          <option value="other">{t.otherCity}</option>
        </select>
        {city === "other" && (
          <>
            <input className="text" value={otherCity} onChange={(e) => setOtherCity(e.target.value)} placeholder={t.otherCity} />
            <div className="chips-grid">
              <Chip on={tier === 1} onClick={() => setTier(1)}>{t.metro}</Chip>
              <Chip on={tier === 2} onClick={() => setTier(2)}>{t.smaller}</Chip>
            </div>
          </>
        )}
      </Q>

      <Q title={t.staff}><Stepper value={staff} min={1} max={500} onChange={setStaff} /></Q>
      <Q title={t.sites}><Stepper value={sites} min={1} max={50} onChange={setSites} /></Q>

      <Q title={t.gst}>
        <div className="chips-grid">
          {t.gstOpts.map((o, i) => <Chip key={o} on={gst === i} onClick={() => setGst(i)}>{o}</Chip>)}
        </div>
      </Q>

      <Q title={t.needs}>
        <div className="chips-grid">
          {NEEDS.map((n) => <Chip key={n.value} on={needs.includes(n.value)} onClick={() => toggle(n.value)}>{n[lang]}</Chip>)}
        </div>
        {NEEDS.filter((n) => n.count && needs.includes(n.value)).map((n) => (
          <div key={n.value} className="count-row">
            <span>{t[n.count === "num_mobile_lines" ? "lines" : n.count === "num_cameras" ? "cameras" : n.count === "num_vehicles" ? "vehicles" : "machines"]}</span>
            <Stepper value={counts[n.count!]} min={1} max={200} onChange={(v) => setCounts({ ...counts, [n.count!]: v })} />
          </div>
        ))}
        <label className="check"><input type="checkbox" checked={noFibre} onChange={(e) => setNoFibre(e.target.checked)} /> {t.fibreNo}</label>
      </Q>

      <Q title={t.budget}>
        <div className="chips-grid">
          {BUDGETS.map((b) => <Chip key={b} on={budget === b} onClick={() => setBudget(b)}>{b ? `Rs ${b.toLocaleString("en-IN")}` : t.noBudget}</Chip>)}
        </div>
      </Q>

      {error && <div className="banner error">{error}</div>}
      <button className="btn primary big" disabled={!ready || busy} onClick={show}>{busy ? "…" : t.show}</button>
      {handoffBox()}
    </div>
  );
}

function Q({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="card q"><h3>{title}</h3>{children}</section>;
}

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return <button type="button" className={`pick ${on ? "on" : ""}`} onClick={onClick}>{children}</button>;
}

function Stepper({ value, min, max, onChange }: { value: number; min: number; max: number; onChange: (v: number) => void }) {
  return (
    <div className="stepper">
      <button type="button" onClick={() => onChange(Math.max(min, value - 1))}>-</button>
      <input type="number" value={value} min={min} max={max}
        onChange={(e) => onChange(Math.min(max, Math.max(min, Number(e.target.value) || min)))} />
      <button type="button" onClick={() => onChange(Math.min(max, value + 1))}>+</button>
    </div>
  );
}
