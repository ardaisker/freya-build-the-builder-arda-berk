// Mock of Freya Bank's statement / debt services (service contract of 1 October 2026, section 5 and 6).
// Every answer for a test customer comes word for word from test-environment/test-customers.json: status code and body.
// A customer, card or week that is not in the file gets the service's 404 from section 4 of the contract, or, where the
// contract has no 404 for the service, a 400 INVALID_ARGUMENTS_ERROR. Token, headers, `call` and `aiFlow` are not checked.
import DATA from "./test-customers.json";

const BY_CUSTOMER = new Map();
const BY_CARD = { "cards.balance": new Map(), "statement.week.get": new Map(), "statement.week.decide": new Map(), "statement.week.change": new Map() };
for (const c of DATA.customers) {
  BY_CUSTOMER.set(String(c.customerNo), c.services || {});
  for (const svc of Object.keys(BY_CARD)) {
    for (const [card, entry] of Object.entries((c.services || {})[svc] || {})) BY_CARD[svc].set(card, entry);
  }
}

const NOT_FOUND = {
  "cards.list": ["FB_IVR_CHANNEL_102", "Müşteriye ait geçerli kart bilgisi bulunamadı."],
  "cards.balance": ["FB_IVR_CHANNEL_120", "Kart bakiye servisi hatası: kart bulunamadı"],
  "statement.week.get": ["FB_IVR_CHANNEL_121", "Hesap kesim haftası servisi hatası: kart bulunamadı"],
  "statement.pdf.send": ["FB_IVR_CHANNEL_107", "Pdf dokümanı bulunamadı"],
};
const SERVICES = ["cards.list", "cards.balance", "statement.week.get", "statement.week.decide", "statement.week.change", "contact.email.get", "statement.pdf.send"];

function guid() {
  return [...crypto.getRandomValues(new Uint8Array(16))].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function errorBody(code, message, type, rootCause) {
  const g = guid();
  return { result: { guid: g, returnCode: code, messageText: message, code, message, type, details: { guid: g, rootCause, errorOrigin: "ivr-gateway-test:ivr-channel-v0" } } };
}

function json(status, body) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" } });
}

const invalid = (message) => ({ http: 400, response: errorBody("INVALID_ARGUMENTS_ERROR", message, "ERROR", "InvalidArgumentsException") });

function missing(service) {
  const nf = NOT_FOUND[service];
  if (nf) return { http: 404, response: errorBody(nf[0], nf[1], "WARNING", "com.freyabank.ivrgateway.ivrchannel.rest.exception.NotFoundException") };
  return invalid("no record for the given arguments");
}

const empty = (v) => v === undefined || v === null || String(v).trim() === "";

function lookup(service, d) {
  if (service === "cards.list" || service === "contact.email.get" || service === "statement.pdf.send") {
    if (empty(d.customerNo)) return invalid("customer number cannot be empty");
    if (service === "contact.email.get" && empty(d.intAddressInfoType)) return invalid("intAddressInfoType cannot be empty");
    if (service === "statement.pdf.send") {
      if (empty(d.cardNumber)) return invalid("card number cannot be empty");
      if (empty(d.emailAddress)) return invalid("email address cannot be empty");
    }
    const services = BY_CUSTOMER.get(String(d.customerNo).trim());
    return (services && services[service]) || missing(service);
  }
  if (empty(d.cardNumber)) return invalid("card number cannot be empty");
  const entry = BY_CARD[service].get(String(d.cardNumber).trim());
  if (service === "cards.balance" || service === "statement.week.get") return entry || missing(service);
  if (empty(d.newStatementWeek)) return invalid("new statement week cannot be empty");
  const week = String(d.newStatementWeek).trim().replace(/\.0+$/, "");
  return (entry && entry[week]) || missing(service);
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "");
    if (path === "" || path === "/health") return json(200, { ok: true, service: "freya-bank-mock", services: SERVICES.map((s) => "/voice/v1/" + s) });
    if (path === "/oauth2/token") return json(200, { access_token: "mock-" + guid(), token_type: "Bearer", expires_in: 1800 });
    const service = path.split("/").pop();
    if (!SERVICES.includes(service) || !(path === "/voice/v1/" + service || path === "/" + service)) return json(404, errorBody("NOT_FOUND", "unknown path", "ERROR", "NotFoundException"));
    if (request.method !== "POST") return json(405, errorBody("METHOD_NOT_ALLOWED", "use POST", "ERROR", "MethodNotAllowed"));
    let body = null;
    try {
      body = JSON.parse(await request.text());
    } catch (e) {
      return json(400, errorBody("INVALID_ARGUMENTS_ERROR", "request body is not JSON", "ERROR", "InvalidArgumentsException"));
    }
    const d = body && typeof body === "object" && body.data && typeof body.data === "object" ? body.data : {};
    const entry = lookup(service, d);
    if (entry.delaySeconds) await new Promise((resolve) => setTimeout(resolve, Number(entry.delaySeconds) * 1000));
    return json(entry.http, entry.response);
  },
};
