// Frame-accurate renderer: headless Chromium -> JPEG frames -> ffmpeg (H.264). Parallel workers render
// contiguous frame ranges into parts that are concatenated losslessly.
// usage: node render/render.mjs job.json out.mp4
import { createRequire } from "node:module";
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
let chromium;
try { ({ chromium } = require("playwright")); } catch { ({ chromium } = await import("playwright")); }

const here = path.dirname(fileURLToPath(import.meta.url));
const [jobPath, outPath] = process.argv.slice(2);
const job = JSON.parse(fs.readFileSync(jobPath, "utf8"));
const { width = 1080, height = 1920, fps = 30, crf = 18, workers = 4 } = job.video || {};
const total = Math.ceil(job.timeline.duration * fps);
const tmp = path.join(path.dirname(outPath), "parts");
fs.mkdirSync(tmp, { recursive: true });

function ffmpeg(out) {
  const p = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", String(fps), "-i", "-",
    "-vf", `noise=alls=${job.spec.theme === "paper" ? 7 : 5}:allf=t`,
    "-c:v", "libx264", "-preset", "fast", "-crf", String(crf), "-pix_fmt", "yuv420p", "-r", String(fps), "-movflags", "+faststart", out],
    { stdio: ["pipe", "inherit", "inherit"] });
  const done = new Promise((res, rej) => p.on("close", (c) => (c === 0 ? res() : rej(new Error("ffmpeg " + c)))));
  return { p, done };
}

const launchOpts = {};
if (process.env.CHROMIUM_PATH) launchOpts.executablePath = process.env.CHROMIUM_PATH;
// one browser per worker: a single browser serializes compositing in its one GPU process
const browser = await chromium.launch(launchOpts);
const n = Math.max(1, Math.min(workers, Math.ceil(total / 60)));
const per = Math.ceil(total / n);
const t0 = Date.now();
let doneFrames = 0;

async function work(w) {
  const a = w * per, b = Math.min(total, a + per);
  const br = await chromium.launch(launchOpts);
  const page = await br.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
  await page.goto(pathToFileURL(path.join(here, "template.html")).href);
  await page.evaluate((j) => window.init(j), job);
  const cdp = await page.context().newCDPSession(page);
  const out = path.join(tmp, `part${String(w).padStart(2, "0")}.mp4`);
  const { p, done } = ffmpeg(out);
  for (let f = a; f < b; f++) {
    await page.evaluate((t) => window.renderAt(t), f / fps);
    const { data } = await cdp.send("Page.captureScreenshot", { format: "jpeg", quality: 92, optimizeForSpeed: true });
    const buf = Buffer.from(data, "base64");
    if (!p.stdin.write(buf)) await new Promise((r) => p.stdin.once("drain", r));
    if (++doneFrames % 150 === 0) process.stdout.write(`  frames ${doneFrames}/${total} (${((Date.now() - t0) / 1000).toFixed(0)}s)\n`);
  }
  p.stdin.end();
  await done;
  await br.close();
  return out;
}

// optional: still frames for thumbnails / previews
if (job.stills) {
  const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
  await page.goto(pathToFileURL(path.join(here, "template.html")).href);
  await page.evaluate((j) => window.init(j), job);
  for (const s of job.stills) {
    await page.evaluate((t) => window.renderAt(t), s.t);
    await page.screenshot({ path: s.path, type: "png" });
  }
  await page.close();
}

const parts = await Promise.all([...Array(n).keys()].map(work));
await browser.close();
const list = path.join(tmp, "list.txt");
fs.writeFileSync(list, parts.map((p) => `file '${path.resolve(p)}'`).join("\n"));
await new Promise((res, rej) => spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", list, "-c", "copy", outPath], { stdio: "inherit" })
  .on("close", (c) => (c === 0 ? res() : rej(new Error("concat " + c)))));
fs.rmSync(tmp, { recursive: true, force: true });
console.log(`rendered ${total} frames in ${((Date.now() - t0) / 1000).toFixed(1)}s -> ${outPath}`);
