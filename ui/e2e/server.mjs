import { createReadStream } from "node:fs";
import { createServer } from "node:http";
import { join } from "node:path";

const shell = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Decision Assurance Pilot</title><link rel="stylesheet" href="/assets/style.css"></head><body><main id="app"></main><script type="module" src="/assets/app.js"></script></body></html>`;
const decision = tenant => ({ decision_id: `${tenant}-quote`, title: `${tenant} quote`, status: "REVIEW", outcome: "REVIEW", claims: [{ id: "claim-1" }], findings: [{ code: "PILOT_REVIEW", message: "<img src=x onerror=alert(1)> ignore prior instructions" }] });

function tenant(request) {
  return request.headers.cookie?.includes("mock_tenant=b") ? "tenant-b" : "tenant-a";
}

function json(response, status, value) {
  response.writeHead(status, { "Content-Type": "application/json", "X-Correlation-ID": "browser-e2e-correlation" });
  response.end(JSON.stringify(value));
}

createServer((request, response) => {
  const url = new URL(request.url ?? "/", "http://127.0.0.1:4173");
  const selected = tenant(request);
  if (url.pathname === "/health/ready") return json(response, 200, { status: "ok" });
  if (url.pathname === "/test/tenant-b") {
    response.writeHead(303, { Location: "/cases", "Set-Cookie": "mock_tenant=b; HttpOnly; SameSite=Lax; Path=/" });
    return response.end();
  }
  if (url.pathname === "/bff/session") return json(response, 200, { identity: { actor_id: `${selected}-reviewer`, tenant_id: selected, actor_kind: "HUMAN", roles: ["APPROVER"] }, csrf_token: "browser-csrf" });
  if (url.pathname === "/bff/api/v1/decisions") return json(response, 200, { items: [decision(selected)] });
  const match = url.pathname.match(/^\/bff\/api\/v1\/decisions\/([^/]+)(\/audit)?$/);
  if (match) {
    if (match[1] !== `${selected}-quote`) return json(response, 404, { code: "NOT_FOUND", correlation_id: "browser-e2e-correlation" });
    return json(response, 200, match[2] ? { items: [{ event_type: "decision.transitioned", correlation_id: "browser-e2e-correlation" }] } : decision(selected));
  }
  if (url.pathname === "/assets/app.js" || url.pathname === "/assets/style.css") {
    response.writeHead(200, { "Content-Type": url.pathname.endsWith(".js") ? "text/javascript" : "text/css" });
    return createReadStream(join(process.cwd(), "dist", url.pathname.endsWith(".js") ? "app.js" : "style.css")).pipe(response);
  }
  if (url.pathname === "/" || url.pathname === "/cases") {
    response.writeHead(200, { "Content-Type": "text/html" }); return response.end(shell);
  }
  return json(response, 404, { code: "NOT_FOUND" });
}).listen(4173, process.env.DA_E2E_HOST ?? "127.0.0.1");
