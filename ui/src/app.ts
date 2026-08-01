import "./style.css";
import { messages, selectLocale, translate, type Locale, type MessageKey } from "./i18n";
import { neverComputesGovernanceOutcome, renderExternalContent, text } from "./render";

type Json = Record<string, unknown>;
type Session = { identity: { actor_id: string; tenant_id: string; actor_kind: string; roles: string[] }; csrf_token: string };

let session: Session | null = null;
let locale: Locale = selectLocale(document.documentElement.lang || navigator.language);

const rootElement = document.querySelector<HTMLElement>("#app");
if (!rootElement) throw new Error("PILOT_UI_ROOT_MISSING");
const root: HTMLElement = rootElement;

function t(key: MessageKey): string { return translate(locale, key); }
function key(): string { return crypto.randomUUID(); }

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("Accept-Language", locale);
  if (init.method && init.method !== "GET") {
    if (!session) throw new Error("AUTHENTICATION_REQUIRED");
    headers.set("X-CSRF-Token", session.csrf_token);
    headers.set("Idempotency-Key", key());
    if (init.body) headers.set("Content-Type", "application/json");
  }
  return fetch(`/bff/api${path}`, { ...init, headers, credentials: "same-origin" });
}

async function json(path: string, init: RequestInit = {}): Promise<Json> {
  const response = await request(path, init);
  if (!response.ok) throw new Error(response.headers.get("X-Correlation-ID") ?? "REQUEST_FAILED");
  return response.json() as Promise<Json>;
}

function button(label: MessageKey, action: () => Promise<void>): HTMLButtonElement {
  const value = document.createElement("button");
  value.type = "button";
  value.textContent = t(label);
  value.addEventListener("click", () => void safe(action));
  return value;
}

async function safe(action: () => Promise<void>): Promise<void> {
  try { await action(); } catch (error) {
    const status = document.querySelector<HTMLElement>("#status-message");
    if (status) status.textContent = `${t("error")} ${error instanceof Error ? error.message : ""}`;
  }
}

function renderShell(): void {
  root.replaceChildren();
  const header = document.createElement("header");
  header.append(text("h1", t("title")));
  const localeButton = document.createElement("button");
  localeButton.textContent = locale === "de" ? "English" : "Deutsch";
  localeButton.addEventListener("click", () => { locale = locale === "de" ? "en" : "de"; document.documentElement.lang = locale; renderShell(); void loadCases(); });
  header.append(localeButton);
  if (session) {
    header.append(text("p", `${session.identity.actor_id} · ${session.identity.tenant_id} · ${session.identity.roles.join(", ")}`, "identity"));
    header.append(button("logout", async () => {
      await fetch("/auth/logout", { method: "POST", headers: { "X-CSRF-Token": session!.csrf_token } });
      session = null; window.location.assign("/auth/end-session");
    }));
  }
  root.append(header, text("p", "", "status-message"));
  root.lastElementChild!.id = "status-message";
  if (!session) return;
  const main = document.createElement("main");
  main.append(caseForm(), intakeLookup(), text("h2", t("cases")));
  const cases = document.createElement("section"); cases.id = "case-list"; main.append(cases);
  const details = document.createElement("section"); details.id = "case-details"; main.append(details);
  root.append(main);
}

function renderLogin(): void {
  root.replaceChildren(text("h1", t("title")));
  const link = document.createElement("a"); link.href = "/auth/login?return_path=/cases"; link.textContent = t("login"); link.className = "primary";
  root.append(link);
}

function caseForm(): HTMLElement {
  const section = document.createElement("section"); section.className = "panel";
  section.append(text("h2", t("newCase")));
  const form = document.createElement("form");
  const id = document.createElement("input"); id.required = true; id.maxLength = 128; id.placeholder = t("intakeId"); id.name = "intake-id";
  const raw = document.createElement("textarea"); raw.required = true; raw.maxLength = 1_000_000; raw.placeholder = t("quoteText"); raw.name = "quote-text";
  const upload = document.createElement("input"); upload.type = "file"; upload.accept = "text/plain,.txt"; upload.ariaLabel = t("upload");
  upload.addEventListener("change", async () => { const file = upload.files?.[0]; if (!file || file.size > 1_000_000 || (file.type && file.type !== "text/plain")) throw new Error("UNSUPPORTED_UPLOAD"); raw.value = await file.text(); });
  const submit = document.createElement("button"); submit.type = "submit"; submit.textContent = t("create");
  form.append(id, raw, upload, submit);
  form.addEventListener("submit", event => { event.preventDefault(); void safe(async () => {
    const record = await json("/v1/intakes", { method: "POST", body: JSON.stringify({ schema_version: "0.3.0", intake_id: id.value, raw_input: raw.value, locale }) });
    renderIntake(record);
  }); });
  section.append(form); return section;
}

function intakeLookup(): HTMLElement {
  const form = document.createElement("form"); form.className = "inline";
  const id = document.createElement("input"); id.placeholder = t("intakeId"); id.required = true;
  const submit = document.createElement("button"); submit.textContent = t("openIntake");
  form.append(id, submit); form.addEventListener("submit", event => { event.preventDefault(); void safe(async () => renderIntake(await json(`/v1/intakes/${encodeURIComponent(id.value)}`))); });
  return form;
}

function renderIntake(record: Json): void {
  const target = document.querySelector<HTMLElement>("#case-details")!; target.replaceChildren(text("h2", String(record.intake_id)), text("p", `${t("status")}: ${record.status}`));
  const verification = record.verification as Json | undefined; const candidates = (verification?.candidates as Json[] | undefined) ?? [];
  for (const candidate of candidates) {
    const row = text("article", `${candidate.fact_type}: ${candidate.normalized_value ?? candidate.raw_value}`, "fact");
    if (record.status === "NEEDS_CONFIRMATION") row.append(button("confirm", async () => {
      const updated = await json(`/v1/intakes/${record.intake_id}/confirmations`, { method: "POST", body: JSON.stringify({ fact_id: candidate.fact_id, action: "CONFIRM", new_value: null, reason: "Human validation in controlled pilot" }) }); renderIntake(updated);
    })); target.append(row);
  }
  if (record.status === "READY") target.append(button("compile", async () => { const decision = await json(`/v1/intakes/${record.intake_id}/compile`, { method: "POST" }); await loadCases(); await renderDecision(decision); }));
}

async function loadCases(): Promise<void> {
  const result = await json("/v1/decisions?limit=50"); const target = document.querySelector<HTMLElement>("#case-list")!; target.replaceChildren();
  for (const item of (result.items as Json[] ?? [])) { const card = document.createElement("button"); card.className = "case-card"; card.append(text("strong", item.title ?? item.decision_id), text("span", `${item.status} · ${item.outcome ?? "—"}`)); card.addEventListener("click", () => void safe(async () => renderDecision(await json(`/v1/decisions/${item.decision_id}`)))); target.append(card); }
}

async function renderDecision(decision: Json): Promise<void> {
  const id = String(decision.decision_id); const target = document.querySelector<HTMLElement>("#case-details")!; target.replaceChildren(text("h2", id), text("p", `${t("status")}: ${decision.status}`), text("p", `${t("outcome")}: ${neverComputesGovernanceOutcome(decision.outcome)}`));
  target.append(text("h3", t("findings"))); renderExternalContent(target.appendChild(document.createElement("div")), (decision.findings as unknown[] | undefined) ?? []);
  const actions = document.createElement("div"); actions.className = "actions";
  actions.append(button("research", async () => {
    const claims = (decision.claims as Json[] | undefined) ?? []; if (!claims.length) throw new Error("CLAIMS_UNAVAILABLE");
    const run = await json("/v1/research-runs", { method: "POST", body: JSON.stringify({ schema_version: "0.4.0", decision_file_id: id, claim_refs: claims.map(claim => claim.id), query: "Verify the public commercial controls for this sales quote", locale: `${locale}-${locale === "de" ? "DE" : "US"}`, preferred_languages: [locale, locale === "de" ? "en" : "de"], max_search_results: 3, max_sources_to_extract: 2, allowed_domains: [], blocked_domains: [], freshness: { maximum_age_days: 365, prefer_recent: true }, research_policy: "standard", force_refresh: false, refresh_generation: null }) }); await pollResearch(String(run.research_run_id), target);
  }));
  actions.append(button("evaluate", async () => { await json(`/v1/decisions/${id}/evaluate`, { method: "POST" }); await renderDecision(await json(`/v1/decisions/${id}`)); }));
  for (const [label, next] of [["validation", "VALIDATION"], ["review", "REVIEW"], ["approve", "APPROVED"]] as const) actions.append(button(label, async () => { const updated = await json(`/v1/decisions/${id}/transitions`, { method: "POST", body: JSON.stringify({ target: next }) }); await renderDecision(updated); }));
  actions.append(button("export", async () => { const response = await request(`/v1/decisions/${id}/export`); if (!response.ok) throw new Error("EXPORT_FAILED"); const url = URL.createObjectURL(await response.blob()); const link = document.createElement("a"); link.href = url; link.download = "decision-assurance-pilot-export.zip"; link.click(); URL.revokeObjectURL(url); }));
  actions.append(button("hold", async () => {
    await request(`/v1/decisions/${id}/legal-hold`, { method: "PUT", body: JSON.stringify({ reason_code: "PILOT_LEGAL_REVIEW" }) });
    await renderDecision(await json(`/v1/decisions/${id}`));
  }));
  actions.append(button("releaseHold", async () => {
    await request(`/v1/decisions/${id}/legal-hold`, { method: "DELETE" });
    await renderDecision(await json(`/v1/decisions/${id}`));
  }));
  actions.append(button("delete", async () => {
    if (!window.confirm(t("deleteConfirm"))) return;
    const deletion = await json(`/v1/decisions/${id}/deletion-requests`, { method: "POST", body: JSON.stringify({ reason_code: "PILOT_USER_REQUEST" }) });
    const requestId = String(deletion.request_id);
    const result = await json(`/v1/deletion-requests/${encodeURIComponent(requestId)}/execute`, { method: "POST" });
    const status = document.querySelector<HTMLElement>("#status-message");
    if (status) status.textContent = `${t("deleteStatus")}: ${String(result.status)}`;
    await loadCases();
  }));
  target.append(actions, text("h3", t("audit")));
  const audit = await json(`/v1/decisions/${id}/audit`); renderExternalContent(target.appendChild(document.createElement("div")), (audit.items as unknown[] | undefined) ?? []);
}

async function pollResearch(runId: string, target: HTMLElement): Promise<void> {
  let run: Json = {}; for (let attempt = 0; attempt < 30; attempt += 1) { run = await json(`/v1/research-runs/${runId}`); if (["COMPLETED", "PARTIALLY_COMPLETED", "FAILED", "CANCELLED"].includes(String(run.status))) break; await new Promise(resolve => setTimeout(resolve, 1000)); }
  target.append(text("p", `Research: ${run.status}`), text("h3", t("sources")), text("p", t("untrusted"), "warning"));
  const sources = await json(`/v1/research-runs/${runId}/sources`); renderExternalContent(target.appendChild(document.createElement("div")), (sources.items as unknown[] | undefined) ?? []);
  target.append(text("h3", t("evidence"))); const evidence = await json(`/v1/research-runs/${runId}/evidence`); renderExternalContent(target.appendChild(document.createElement("div")), (evidence.items as unknown[] | undefined) ?? []);
}

async function start(): Promise<void> {
  const response = await fetch("/bff/session", { credentials: "same-origin" }); if (response.status === 401) { renderLogin(); return; }
  session = await response.json() as Session; renderShell(); await safe(loadCases);
}

void start();

export { messages };
