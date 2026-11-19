// Controllo di sintassi di ogni file JS di assets/ e degli <script> inline degli HTML.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import vm from "node:vm";

const dir = "assets";
let errors = 0;
for (const f of readdirSync(dir)) {
  const p = join(dir, f);
  const chunks = [];
  if (f.endsWith(".js")) chunks.push(readFileSync(p, "utf8"));
  if (f.endsWith(".html")) {
    const html = readFileSync(p, "utf8");
    for (const m of html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)) chunks.push(m[1]);
  }
  chunks.forEach((code, i) => {
    try {
      new vm.Script(code, { filename: `${p}#${i}` });
    } catch (e) {
      errors++;
      console.error(`ERRORE ${p} (blocco ${i}): ${e.message}`);
    }
  });
  if (chunks.length) console.log(`ok  ${p} (${chunks.length} blocchi)`);
}
process.exit(errors ? 1 : 0);
