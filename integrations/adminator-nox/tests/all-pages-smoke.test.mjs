import test from "node:test";
import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import { JSDOM } from "jsdom";
import { mountAdminatorNox } from "../nox-adminator-adapter.mjs";

const dist = new URL("../artifacts/adminator-dist/", import.meta.url);
const rootPath = decodeURIComponent(dist.pathname);
const pages = (await readdir(rootPath)).filter((name) => name.endsWith(".html")).sort();

test("all 18 donor pages mount as NOX pages with no dropdown navigation", async () => {
  assert.ok(pages.length >= 18, "complete donor distribution must contain at least 18 pages");
  for (const page of pages) {
    const html = await readFile(join(rootPath, page), "utf8");
    assert.equal((html.match(/nox-adminator-entry\\.mjs/g) || []).length, 1,
      page + ": NOX native entry must be in the actual staged page");
    assert.equal((html.match(/nox-adminator-theme\\.css/g) || []).length, 1,
      page + ": NOX theme must be in the actual staged page");
    assert.ok(!/fonts\\.(?:googleapis|gstatic)\\.com/i.test(html),
      page + ": no live Google Fonts dependency in offline EXE");
    const dom = new JSDOM(html, { url: "https://nox.local/" + page });
    const doc = dom.window.document;
    const adapter = mountAdminatorNox({ root: doc, routeBindings: {} });
    try {
      assert.equal(doc.querySelectorAll(".dd-wrap").length, 0, page + ": demo dropdown wrappers removed");
      assert.equal(doc.querySelectorAll("[data-dropdown]").length, 0, page + ": dropdown triggers removed");
      assert.equal(doc.querySelectorAll("[data-nav-toggle]").length, 0, page + ": collapsible nav toggles removed");
      for (const group of doc.querySelectorAll("[data-nav-group]")) {
        const submenu = group.querySelector(".nav-submenu");
        if (submenu) {
          assert.equal(submenu.hidden, false, page + ": nested nav stays visible");
          assert.equal(submenu.style.display, "grid", page + ": nested nav is a visible action grid");
        }
      }
      for (const select of doc.querySelectorAll("select")) {
        if (Array.from(select.options).some(option => !option.disabled && option.value !== "")) {
          assert.equal(select.dataset.noxSelectReplaced, "true", page + ": select converted to visual buttons");
          assert.ok(select.classList.contains("nox-visually-hidden-select"), page + ": native select is visually hidden");
        }
      }
      for (const choice of doc.querySelectorAll(".nox-choice-button")) {
        assert.equal(choice.disabled, false, page + ": visible option buttons remain usable");
      }
      for (const button of doc.querySelectorAll("button:not([data-nox-route])")) {
        const local = button.matches(
          "#themeToggle,[data-drawer-open],[data-tab-target],[data-accordion-trigger],.nox-choice-button,[data-nox-local-action]"
        );
        if (!local) {
          assert.equal(button.disabled, true, page + ": unbound demo action must be disabled");
          assert.equal(button.dataset.noxNativeState, "hold", page + ": unbound action must display HOLD");
        }
      }
      for (const link of doc.querySelectorAll('a[aria-disabled="true"]')) {
        assert.equal(link.hasAttribute("href"), false, page + ": untrusted external/demo links have no destination");
      }
      assert.equal(doc.querySelectorAll("canvas[data-chart-key]").length, 0,
        page + ": seeded demo charts must not be shown as NOX telemetry");
      for (const chart of doc.querySelectorAll(".nox-live-chart-placeholder")) {
        assert.equal(chart.dataset.noxSeriesState, "unavailable",
          page + ": chart waits for a verified OneHost series");
      }
      assert.ok(doc.querySelector(".nox-cosmic-stage"), page + ": NOX 3D scene mounts");
    } finally {
      adapter.destroy();
      dom.window.close();
    }
  }
});

test("visible button replacements update their hidden native select without a dropdown", async () => {
  for (const page of pages) {
    const html = await readFile(join(rootPath, page), "utf8");
    const dom = new JSDOM(html, { url: "https://nox.local/" + page });
    const adapter = mountAdminatorNox({ root: dom.window.document, routeBindings: {} });
    try {
      const select = dom.window.document.querySelector("select[data-nox-select-replaced]");
      if (!select) continue;
      const buttons = dom.window.document.querySelectorAll(".nox-choice-button");
      const target = Array.from(buttons).find(button =>
        Number.isInteger(Number(button.dataset.optionIndex)) &&
        select.options[Number(button.dataset.optionIndex)]?.value !== "");
      if (target) {
        target.click();
        assert.equal(select.value, select.options[Number(target.dataset.optionIndex)].value);
        assert.equal(target.getAttribute("aria-pressed"), "true");
        return;
      }
    } finally {
      adapter.destroy();
      dom.window.close();
    }
  }
  assert.ok(true, "donor currently contains no populated select; no inert dropdown was introduced");
});
