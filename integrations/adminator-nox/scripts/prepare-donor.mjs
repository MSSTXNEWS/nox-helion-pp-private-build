import { createHash } from "node:crypto";
import { cp, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const packageRoot = resolve(here, "..");
const donorRoot = join(packageRoot, "node_modules", "adminator-admin-dashboard");
const distRoot = join(donorRoot, "dist");
const outputRoot = join(packageRoot, "artifacts", "adminator-dist");
const donorMeta = JSON.parse(await readFile(join(donorRoot, "package.json"), "utf8"));
if (donorMeta.version !== "4.4.0" || donorMeta.license !== "MIT") {
  throw new Error("ADMINATOR_VERSION_OR_LICENSE_MISMATCH");
}
const walk = async (dir) => {
  const entries = await readdir(dir, { withFileTypes: true });
  const out = [];
  for (const entry of entries) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...await walk(full));
    else out.push(full);
  }
  return out;
};
const donorFiles = await walk(distRoot);
const pages = donorFiles.filter((file) => file.toLowerCase().endsWith(".html"));
if (pages.length < 18) throw new Error("ADMINATOR_EXPECTED_18_STATIC_PAGES");
await mkdir(dirname(outputRoot), { recursive: true });
await cp(distRoot, outputRoot, { recursive: true, force: true });
await cp(join(packageRoot, "nox-adminator-theme.css"), join(outputRoot, "nox-adminator-theme.css"));
await cp(join(packageRoot, "nox-adminator-entry.mjs"), join(outputRoot, "nox-adminator-entry.mjs"));
let adapter = await readFile(join(packageRoot, "nox-adminator-adapter.mjs"), "utf8");
adapter = adapter.replace(
  '"../../proposals/P01/WOW-MAX10/route-dispatch.mjs"',
  '"./nox-route-dispatch.mjs"'
);
if (adapter.includes("../../proposals/P01/WOW-MAX10/route-dispatch.mjs")) {
  throw new Error("NOX_NATIVE_DISPATCHER_IMPORT_REWRITE_FAILED");
}
await writeFile(join(outputRoot, "nox-adminator-adapter.mjs"), adapter);
const canonicalDispatcher = resolve(packageRoot, "../../proposals/P01/WOW-MAX10/route-dispatch.mjs");
await cp(canonicalDispatcher, join(outputRoot, "nox-route-dispatch.mjs"));
for (const page of pages) {
  let html = await readFile(page, "utf8");
  if (!html.includes("nox-adminator-entry.mjs")) {
    const injection = '<link rel="stylesheet" href="./nox-adminator-theme.css">\n' +
      '<script type="module" src="./nox-adminator-entry.mjs"></script>';
    html = html.replace(/<\/body>/i, injection + "\n</body>");
    if (!html.includes("nox-adminator-entry.mjs")) throw new Error("ADMINATOR_PAGE_INJECTION_FAILED");
    await writeFile(page, html);
  }
}
const outputFiles = await walk(outputRoot);
const manifest = [];
for (const file of outputFiles.sort()) {
  const bytes = await readFile(file);
  manifest.push({
    path: relative(outputRoot, file).replaceAll("\\", "/"),
    size: bytes.length,
    sha256: createHash("sha256").update(bytes).digest("hex")
  });
}
await writeFile(join(outputRoot, "NOX_ADMINATOR_SOURCE_MANIFEST.json"), JSON.stringify({
  donor: "adminator-admin-dashboard",
  version: "4.4.0",
  license: "MIT",
  pageCount: pages.length,
  generatedAt: new Date().toISOString(),
  files: manifest
}, null, 2) + "\n");
console.log(JSON.stringify({ donor: donorMeta.name, version: donorMeta.version,
  pages: pages.length, files: manifest.length, output: outputRoot }, null, 2));
