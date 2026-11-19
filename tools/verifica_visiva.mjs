// Un solo comando: avvia il server di verifica (mock), esegue i passi, lo chiude.
// Uso: node tools/verifica_visiva.mjs [passi.json] [cartella_screenshot]
import { spawn } from "node:child_process";

const steps = process.argv[2] || "tests/visivi/flusso_completo.json";
const out = process.argv[3] || "tests/_out/screenshot";
const PY = process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python";

const server = spawn(PY, ["tools/server_verifica.py", "--port", "8765"], { stdio: ["ignore", "inherit", "inherit"] });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let ready = false;
for (let i = 0; i < 60 && !ready; i++) {
  try { ready = (await fetch("http://127.0.0.1:8765/index.html")).ok; } catch { await sleep(250); }
}
if (!ready) { console.error("Server di verifica non partito"); server.kill(); process.exit(2); }

const run = spawn(process.execPath, ["tools/cdp.mjs", steps, out], { stdio: "inherit" });
const code = await new Promise(r => run.on("exit", r));
server.kill();
process.exit(code ?? 1);
