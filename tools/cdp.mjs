// Pilota Chrome headless via DevTools Protocol leggendo una lista di passi JSON.
// Uso: node tools/cdp.mjs passi.json [cartella_screenshot]
// Passi: {"w":1024,"h":700} | {"nav":"url"} | {"wait":ms} | {"eval":"js"} | {"shot":"nome"}
//        {"click":"selettore"} | {"scenario":{...}} (POST al server di verifica) | {"log":"testo"}
// Alla fine stampa errori della console, eccezioni e chiamate API fallite. Esce con 1 se ce ne sono.
// Chrome gira con rete esterna bloccata (solo 127.0.0.1).
import { spawn } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync, existsSync, mkdtempSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

const [, , stepsFile, outDir = "tests/_out/screenshot"] = process.argv;
if (!stepsFile) { console.error("Uso: node tools/cdp.mjs passi.json [cartella]"); process.exit(2); }
const steps = JSON.parse(readFileSync(stepsFile, "utf8"));
mkdirSync(outDir, { recursive: true });

const CHROME = [
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
].find(existsSync);
const PORT = 9333;
const profile = mkdtempSync(join(tmpdir(), "cdp-prenotazioni-"));
const chrome = spawn(CHROME, [
  "--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
  "--no-first-run", "--no-default-browser-check", "--disable-extensions",
  "--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1",
  "--hide-scrollbars", "about:blank",
], { stdio: "ignore" });

const sleep = ms => new Promise(r => setTimeout(r, ms));
let target;
for (let i = 0; i < 50 && !target; i++) {
  try {
    const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
    target = list.find(t => t.type === "page");
  } catch { await sleep(200); }
}
if (!target) { console.error("Chrome non raggiungibile"); chrome.kill(); process.exit(2); }

const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise(r => ws.addEventListener("open", r, { once: true }));
let seq = 0;
const pending = new Map();
const problems = [];
ws.addEventListener("message", ev => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    const { res, rej } = pending.get(m.id);
    pending.delete(m.id);
    m.error ? rej(new Error(m.error.message)) : res(m.result);
    return;
  }
  if (m.method === "Runtime.consoleAPICalled" && ["error", "assert"].includes(m.params.type)) {
    problems.push("console.error: " + m.params.args.map(a => a.value ?? a.description).join(" "));
  }
  if (m.method === "Runtime.exceptionThrown") {
    const d = m.params.exceptionDetails;
    problems.push("eccezione: " + (d.exception?.description || d.text));
  }
  if (m.method === "Network.responseReceived" && m.params.response.status >= 400) {
    problems.push(`HTTP ${m.params.response.status}: ${m.params.response.url}`);
  }
});
const send = (method, params = {}) => new Promise((res, rej) => {
  const id = ++seq;
  pending.set(id, { res, rej });
  ws.send(JSON.stringify({ id, method, params }));
});

await send("Runtime.enable");
await send("Page.enable");
await send("Network.enable");
let w = 1600, h = 900;

for (const s of steps) {
  if (s.w) {
    w = s.w; h = s.h || h;
    await send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 1, mobile: false });
  } else if (s.nav) {
    await send("Page.navigate", { url: s.nav });
    await sleep(600);
  } else if (s.wait) {
    await sleep(s.wait);
  } else if (s.scenario) {
    const base = new URL(steps.find(x => x.nav)?.nav || "http://127.0.0.1:8765/").origin;
    await fetch(base + "/__scenario", { method: "POST", body: JSON.stringify(s.scenario) });
  } else if (s.click) {
    const r = await send("Runtime.evaluate", {
      expression: `(() => { const el = document.querySelector(${JSON.stringify(s.click)}); if (!el) return "NON TROVATO"; el.click(); return "ok"; })()`,
      returnByValue: true,
    });
    if (r.result.value !== "ok") problems.push(`click ${s.click}: ${r.result.value}`);
  } else if (s.eval) {
    const r = await send("Runtime.evaluate", { expression: s.eval, awaitPromise: true, returnByValue: true });
    const v = r.exceptionDetails ? "ECCEZIONE " + (r.exceptionDetails.exception?.description || r.exceptionDetails.text) : r.result.value;
    console.log(`[eval] ${s.label || s.eval.slice(0, 60)} → ${typeof v === "string" ? v : JSON.stringify(v)}`);
    if (s.expect !== undefined && JSON.stringify(v) !== JSON.stringify(s.expect)) {
      problems.push(`ATTESO ${JSON.stringify(s.expect)} ma ottenuto ${JSON.stringify(v)} (${s.label || s.eval.slice(0, 60)})`);
    }
  } else if (s.shot) {
    const r = await send("Page.captureScreenshot", { format: "png" });
    const file = join(outDir, `${s.shot}.png`);
    writeFileSync(file, Buffer.from(r.data, "base64"));
    console.log(`[shot] ${file} (${w}x${h})`);
  } else if (s.log) {
    console.log(`--- ${s.log}`);
  }
}

ws.close();
chrome.kill();
if (problems.length) {
  console.log("\nPROBLEMI:");
  problems.forEach(p => console.log("  - " + p));
  process.exit(1);
}
console.log("\nNessun errore in console, nessuna chiamata fallita, attese rispettate.");
