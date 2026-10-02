// Builds handbook.html from handbook.src.html (styles and figures are reused from
// ../architecture/architecture.html) and renders ../Netra-Technical-Handbook.pdf.
// Usage: node build-pdf.mjs   (needs Google Chrome and `npm i puppeteer-core`)
import puppeteer from "puppeteer-core";
import { fileURLToPath, pathToFileURL } from "node:url";
import fs from "node:fs";
import path from "node:path";

const here = process.env.HANDBOOK_DIR || path.dirname(fileURLToPath(import.meta.url));
const arch = fs.readFileSync(path.join(here, "..", "architecture", "architecture.html"), "utf8");
let html = fs.readFileSync(path.join(here, "handbook.src.html"), "utf8");

const css = arch.slice(arch.indexOf("<style>") + 7, arch.indexOf("</style>"));
html = html.replace("{{CSS}}", css);
html = html.replace(/\{\{SVG:(Figure \d+)\}\}/g, (_, fig) => {
  const cap = arch.indexOf(`<div class="caption">${fig} —`);
  if (cap < 0) throw new Error(`${fig} not found`);
  const start = arch.lastIndexOf("<svg", cap);
  return arch.slice(start, arch.indexOf("</svg>", start) + 6);
});
const out = path.join(here, "handbook.html");
fs.writeFileSync(out, html);

const chrome = process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const browser = await puppeteer.launch({ executablePath: chrome, headless: "new" });
const page = await browser.newPage();
await page.goto(pathToFileURL(out).href, { waitUntil: "load" });
await page.pdf({
  path: path.join(here, "..", "Netra-Technical-Handbook.pdf"),
  format: "A4",
  printBackground: true,
  preferCSSPageSize: true,
  displayHeaderFooter: true,
  headerTemplate: "<span></span>",
  footerTemplate: `<div style="font-family:Helvetica,Arial,sans-serif;font-size:7.5px;color:#64748b;width:100%;padding:0 15mm;display:flex;justify-content:space-between">
    <span>Netra — Technical Handbook · okDriver Full Stack Developer Challenge</span>
    <span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>`,
  margin: { top: "16mm", bottom: "18mm", left: "15mm", right: "15mm" },
});
await browser.close();
console.log("wrote docs/Netra-Technical-Handbook.pdf");
