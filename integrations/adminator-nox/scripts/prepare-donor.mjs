import { createHash } from "node:crypto";
import { cp, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
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

async function walk(dir) {
  const out = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...await walk(full));
    else out.push(full);
  }
  return out;
}

const donorFiles = await walk(distRoot);
const pages = donorFiles.filter((file) => file.toLowerCase().endsWith(".html"));
if (pages.length !== 18) throw new Error("ADMINATOR_EXPECTED_EXACTLY_18_STATIC_PAGES");

await rm(outputRoot, { recursive: true, force: true });
await mkdir(dirname(outputRoot), { recursive: true });
await cp(distRoot, outputRoot, { recursive: true });
await cp(join(packageRoot, "nox-adminator-theme.css"), join(outputRoot, "nox-adminator-theme.css"));
await cp(join(packageRoot, "nox-adminator-entry.mjs"), join(outputRoot, "nox-adminator-entry.mjs"));

let adapter = await readFile(join(packageRoot, "nox-adminator-adapter.mjs"), "utf8");
// Stage the ORIGINAL OneHost client in the donor distribution. The client is
// not bundled into a second backend. Its relative imports are copied intact.
const hostBundle = [
  "ui/onehost-menu-bindings.mjs",
  "ui/selfbuilder-menu-v2.mjs",
  "ui/selfbuilder-wow-workbench.mjs",
  "ui/nox-r11-wow.mjs",
  "proposals/P01/WOW-MAX10/scene-contract.mjs"
];
const repositoryRoot = resolve(packageRoot, "../..");
for (const relativePath of hostBundle) {
  const source = resolve(repositoryRoot, relativePath);
  const target = join(outputRoot, "nox-native", relativePath);
  if (!source.startsWith(repositoryRoot + "/") && source !== repositoryRoot) {
    throw new Error("NOX_NATIVE_SOURCE_OUTSIDE_REPO");
  }
  const bytes = await readFile(source);
  if (bytes.length === 0 || bytes.length > 2000000) {
    throw new Error("NOX_NATIVE_MODULE_SOURCE_SIZE_HOLD:" + relativePath);
  }
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, bytes);
}
const importBefore = 'from "../../ui/onehost-menu-bindings.mjs"';
const importAfter = 'from "./nox-native/ui/onehost-menu-bindings.mjs"';
if (!adapter.includes(importBefore)) throw new Error("NOX_NATIVE_CLIENT_IMPORT_ANCHOR_HOLD");
adapter = adapter.replace(importBefore, importAfter);
if (adapter.includes(importBefore) || !adapter.includes(importAfter)) {
  throw new Error("NOX_NATIVE_CLIENT_RELATIVE_REWRITE_HOLD");
}
await writeFile(join(outputRoot, "nox-adminator-adapter.mjs"), adapter);

for (const page of pages) {
  let html = await readFile(page, "utf8");
  html = html.replace(/<link[^>]+(?:fonts\.googleapis\.com|fonts\.gstatic\.com)[^>]*>\s*/gi, "");
  html = html.replace(/<iframe([^>]*src=["'][^"']*(?:google\.com\/maps|maps\.googleapis\.com)[^"']*["'][^>]*)><\/iframe>/gi,
    '<div class="nox-external-resource-hold" role="status">MAP PROVIDER NOT CONNECTED</div>');
  const injection = '<link rel="stylesheet" href="./nox-adminator-theme.css">\n' +
    '<script type="module" src="./nox-adminator-entry.mjs"></script>';
  if (!html.includes("nox-adminator-entry.mjs")) {
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
const report = {
  donor: "adminator-admin-dashboard",
  version: "4.4.0",
  license: "MIT",
  pageCount: pages.length,
  fileCount: manifest.length,
  files: manifest
};
await writeFile(join(outputRoot, "NOX_ADMINATOR_SOURCE_MANIFEST.json"), JSON.stringify(report, null, 2) + "\n");
console.log(JSON.stringify({
  donor: donorMeta.name, version: donorMeta.version,
  pages: pages.length, files: manifest.length, output: outputRoot
}, null, 2));
