// Renders architecture.html to ../Netra-Architecture.pdf (A4, page numbers).
// Usage: node build-pdf.mjs   (needs Google Chrome and `npm i puppeteer-core`)
import puppeteer from "puppeteer-core";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const chrome = process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const browser = await puppeteer.launch({ executablePath: chrome, headless: "new" });
const page = await browser.newPage();
await page.goto(pathToFileURL(path.join(here, "architecture.html")).href, { waitUntil: "load" });
await page.pdf({
  path: path.join(here, "..", "Netra-Architecture.pdf"),
  format: "A4",
  printBackground: true,
  preferCSSPageSize: true,
  displayHeaderFooter: true,
  headerTemplate: "<span></span>",
  footerTemplate: `<div style="font-family:Helvetica,Arial,sans-serif;font-size:7.5px;color:#64748b;width:100%;padding:0 15mm;display:flex;justify-content:space-between">
    <span>Netra — System Architecture · okDriver Full Stack Developer Challenge</span>
    <span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>`,
  margin: { top: "16mm", bottom: "18mm", left: "15mm", right: "15mm" },
});
await browser.close();
console.log("wrote docs/Netra-Architecture.pdf");
