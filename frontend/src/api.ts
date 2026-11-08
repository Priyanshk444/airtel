// Typed client for the backend. Types mirror backend/app/engine/models.py, quote.py and orders.py.

export interface Reason {
  code: string;
  message: string;
  related_product_id?: string | null;
  related_need?: string | null;
}

export interface BundleItem {
  product_id: string;
  product_name: string;
  category: string;
  unit: string;
  quantity: number;
  unit_price_inr: number;
  monthly_inr: number;
  setup_inr: number;
  min_contract_months: number;
  install_days: number;
  is_core: boolean;
  serves_need?: string | null;
  reasons: Reason[];
}

export interface Exclusion {
  product_id: string;
  product_name: string;
  reasons: Reason[];
  alternative_product_id?: string | null;
  alternative_product_name?: string | null;
}

export interface AddOn {
  product_id: string;
  product_name: string;
  category: string;
  unit: string;
  description: string;
  default_quantity: number;
  unit_price_inr: number;
  monthly_inr: number;
  setup_inr: number;
  min_contract_months: number;
  install_days: number;
  why: string;
}

export interface Pricing {
  monthly_total_inr: number;
  setup_total_inr: number;
  contract_months: number;
  expected_install_days: number;
  first_bill_inr: number;
  budget_status: string;
  budget_gap_inr: number;
}

export interface Recommendation {
  segment: string;
  segment_label: string;
  segment_inferred: boolean;
  items: BundleItem[];
  excluded: Exclusion[];
  add_ons: AddOn[];
  pricing: Pricing;
  warnings: string[];
  kyc_path: string;
}

export interface TranscriptEntry {
  role: "user" | "assistant";
  text: string;
}

export interface AdvisorState {
  session_id: string;
  reply: string;
  stage: "collecting" | "recommended" | "handoff";
  language?: string | null;
  profile: Record<string, unknown>;
  recommendation: Recommendation | null;
  handoff_id?: string | null;
  transcript: TranscriptEntry[];
  llm_available?: boolean;
}

export interface QuoteLine {
  product_id: string;
  quantity: number;
}

export interface QuoteIssue {
  product_id: string;
  product_name: string;
  message: string;
  severity: "blocking" | "info";
}

export interface QuoteResponse {
  items: BundleItem[];
  pricing: Pricing;
  issues: QuoteIssue[];
  kyc_path: string;
}

export interface TimelineStep {
  status: string;
  label: string;
  expected_at: string;
  done_at: string | null;
}

export interface Order {
  id: string;
  session_id: string | null;
  kyc_case_id: string | null;
  created_at: string;
  business_name: string;
  city: string | null;
  items: BundleItem[];
  pricing: Pricing;
  payment: { status: string; method: string; amount_inr: number; message: string; transaction_id?: string };
  timeline: TimelineStep[];
  current_status: string;
}

async function http<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, { headers: { "Content-Type": "application/json" }, ...init });
  if (!res.ok) {
    let detail = "";
    try {
      detail = (await res.json()).detail ?? "";
    } catch {
      detail = await res.text();
    }
    throw new Error(detail || `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

const baseApi = {
  // advisor
  newSession: (assistedBy?: string, seedProfile?: Record<string, unknown>) =>
    http<AdvisorState>("/api/advisor/sessions", {
      method: "POST",
      body: JSON.stringify({ assisted_by: assistedBy ?? null, seed_profile: seedProfile ?? null }),
    }),
  getSession: (id: string) => http<AdvisorState>(`/api/advisor/sessions/${id}`),
  sendMessage: (id: string, message: string) =>
    http<AdvisorState>(`/api/advisor/sessions/${id}/messages`, { method: "POST", body: JSON.stringify({ message }) }),
  health: () => http<{ status: string; llm_available: boolean; advisor_model: string }>("/api/health"),
  guided: (id: string, answers: Record<string, unknown>, summaryLine?: string) =>
    http<AdvisorState>(`/api/advisor/sessions/${id}/guided`, { method: "POST", body: JSON.stringify({ answers, summary_line: summaryLine ?? null }) }),
  handoff: (id: string, reason: string, callback: string | null) =>
    http<AdvisorState>(`/api/advisor/sessions/${id}/handoff`, { method: "POST", body: JSON.stringify({ reason, callback }) }),
  // quote & orders
  quote: (body: { session_id?: string | null; profile?: Record<string, unknown>; lines: QuoteLine[] }) =>
    http<QuoteResponse>("/api/quote", { method: "POST", body: JSON.stringify(body) }),
  placeOrder: (body: {
    session_id?: string | null;
    profile?: Record<string, unknown>;
    lines: QuoteLine[];
    customer: { business_name: string; contact_name?: string | null; phone?: string | null; city?: string | null };
    payment: { method: string; reference?: string | null };
  }) => http<Order>("/api/orders", { method: "POST", body: JSON.stringify(body) }),
  getOrder: (id: string) => http<Order>(`/api/orders/${id}`),
  listOrders: (sessionId?: string) => http<Order[]>(`/api/orders${sessionId ? `?session_id=${sessionId}` : ""}`),
  advance: (id: string, to?: string) =>
    http<Order>(`/api/orders/${id}/advance`, { method: "POST", body: JSON.stringify({ to_status: to ?? null }) }),
};

export const inr = (n: number) => "Rs " + n.toLocaleString("en-IN");

// --- KYC ----------------------------------------------------------------------------------
export interface ConsentPurpose {
  key: string;
  required: boolean;
  title: string;
  what: string;
  why: string;
  retention: string;
}
export interface KycCheck {
  code: string;
  title: string;
  status: "pass" | "fail" | "review" | "not_applicable";
  reason: string;
  documents: string[];
}
export interface KycCase {
  id: string;
  session_id: string | null;
  path: string;
  status: "in_progress" | "verified" | "needs_review" | "failed";
  created_at: string;
  retention_until: string;
  documents: Record<string, Record<string, unknown>>;
  checks: { overall?: string; summary?: string; checks?: KycCheck[] };
  required_documents: string[];
}
export interface Specimen {
  applicant: string;
  business_name: string;
  documents: string[];
}

export const kycApi = {
  consentPurposes: () => http<ConsentPurpose[]>("/api/kyc/consent/purposes"),
  giveConsent: (session_id: string, purposes: Record<string, boolean>) =>
    http<unknown>("/api/kyc/consent", { method: "POST", body: JSON.stringify({ session_id, purposes }) }),
  newCase: (session_id: string, order_id?: string | null) =>
    http<KycCase>("/api/kyc/cases", { method: "POST", body: JSON.stringify({ session_id, order_id: order_id ?? null }) }),
  getCase: (id: string) => http<KycCase>(`/api/kyc/cases/${id}`),
  uploadSpecimen: (id: string, applicant: string, doc_type: string) =>
    http<KycCase>(`/api/kyc/cases/${id}/documents/specimen`, { method: "POST", body: JSON.stringify({ applicant, doc_type }) }),
  uploadDocument: async (id: string, doc_type: string, file: File): Promise<KycCase> => {
    const form = new FormData();
    form.append("doc_type", doc_type);
    form.append("file", file);
    const res = await fetch(`/api/kyc/cases/${id}/documents`, { method: "POST", body: form });
    if (!res.ok) {
      let detail = "";
      try { detail = (await res.json()).detail ?? ""; } catch { detail = await res.text(); }
      throw new Error(detail || `${res.status} ${res.statusText}`);
    }
    return res.json();
  },
  specimens: () => http<Specimen[]>("/api/kyc/specimens"),
};



// --- partner back office ------------------------------------------------------------------
export interface HandoffLead {
  id: string;
  session_id: string;
  created_at: string;
  reason: string;
  summary: string;
  contact: string | null;
  city: string | null;
  state: string | null;
  segment: string | null;
  status: string;
  profile: Record<string, unknown>;
  recommendation: Recommendation | null;
  transcript: TranscriptEntry[];
}
export interface PropensityLead {
  lead_id: string;
  business_name: string;
  business_type: string;
  segment: string;
  city: string;
  state: string;
  lead_source: string;
  stage_reached: string;
  has_gstin: boolean;
  employee_count: number;
  preferred_language: string;
  contact_name: string;
  score: number;
  reasons: string[];
}
export interface PropensityModel {
  metrics: { test_leads: number; activation_rate_baseline: number; roc_auc: number; average_precision: number; precision_top10pct: number; lift_top10pct: number; recall_top20pct: number; note: string };
  top_factors: { factor: string; weight: number; direction: "raises" | "lowers" }[];
  features_used: string[];
}
export interface PartnerSession {
  id: string;
  created_at: string;
  updated_at: string;
  stage: string;
  assisted_by: string | null;
  profile: Record<string, unknown>;
  handoff_id: string | null;
  monthly_total_inr: number | null;
  segment_label: string | null;
  order: { id: string; current_status: string } | null;
}

const qs = (p: Record<string, string | number | undefined>) =>
  Object.entries(p).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&");

export const partnerApi = {
  handoffs: (p: { state?: string; city?: string; status?: string }) => http<HandoffLead[]>(`/api/handoffs?${qs(p)}`),
  updateHandoff: (id: string, status: string) => http<HandoffLead>(`/api/handoffs/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }),
  propensityLeads: (p: { state?: string; city?: string; segment?: string; limit?: number }) => http<PropensityLead[]>(`/api/propensity/leads?${qs(p)}`),
  propensityModel: () => http<PropensityModel>("/api/propensity/model"),
  territories: () => http<Record<string, string[]>>("/api/partner/territories"),
  partnerSessions: (assistedBy: string) => http<PartnerSession[]>(`/api/partner/sessions?${qs({ assisted_by: assistedBy })}`),
};
export const api = { ...baseApi, ...kycApi, ...partnerApi };
