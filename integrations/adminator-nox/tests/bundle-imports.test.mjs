import test from "node:test";
import assert from "node:assert/strict";
import { readFile, stat } from "node:fs/promises";
import { resolve, dirname, relative, isAbsolute } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../artifacts/adminator-dist");
const assets = [
  "nox-adminator-adapter.mjs",
  "nox-adminator-entry.mjs",
  "nox-native/ui/onehost-menu-bindings.mjs",
  "nox-native/ui/selfbuilder-menu-v2.mjs",
  "nox-native/ui/selfbuilder-wow-workbench.mjs",
  "nox-native/ui/nox-r11-wow.mjs",
  "nox-native/proposals/P01/WOW-MAX10/scene-contract.mjs"
];

test("offline native bundle contains only internally resolvable imports", async () => {
  for (const asset of assets) {
    const sourcePath = resolve(root, asset);
    assert.ok(!relative(root, sourcePath).startsWith(".."), asset + " outside dist");
    const text = await readFile(sourcePath, "utf8");
    const rx = /^\s*import\s+(?:[^;\n]*?\s+from\s+)?["']([^"']+)["']/gm;
    for (const match of text.matchAll(rx)) {
      const specifier = match[1];
      assert.ok(specifier.startsWith("./") || specifier.startsWith("../"),
        asset + ": external or absolute import " + specifier);
      const importPath = resolve(dirname(sourcePath), specifier);
      assert.ok(!relative(root, importPath).startsWith(".."),
        asset + ": import escapes distribution " + specifier);
      assert.ok((await stat(importPath)).isFile(),
        asset + ": missing import " + specifier);
    }
  }
  const adapter = await readFile(resolve(root,"nox-adminator-adapter.mjs"),"utf8");
  assert.ok(adapter.includes('from "./nox-native/ui/onehost-menu-bindings.mjs"'));
  assert.ok(!adapter.includes('from "/ui/onehost-menu-bindings.mjs"'));
});
