import { createNativeMenuClient } from "../../ui/onehost-menu-bindings.mjs";

// Exact action route IDs already admitted by ui/onehost-menu-bindings.mjs.
// Legacy menu labels (e.g. "model-library") are screen IDs, not native routes.
export const NOX_NATIVE_ROUTES = Object.freeze([
  "helion.chat", "chat.history", "chat.stop", "chat.model", "chat.commands",
  "models.catalog", "models.queue", "models.preflight", "models.pull",
  "models.cancel", "models.retry", "models.gguf.import", "gpu.preflight",
  "training.start", "system.autostart", "browser.open", "browser.navidle",
  "menu.dispatch", "menu.binding"
]);
const routeSet = new Set(NOX_NATIVE_ROUTES);
const safeNumber = (value) => Number.isFinite(value) && value >= 0 && value <= 100;
const svgNS = "http://www.w3.org/2000/svg";

export function validateRouteBindings(bindings = {}) {
  if (!bindings || typeof bindings !== "object" || Array.isArray(bindings)) {
    throw new TypeError("NOX_ROUTE_BINDINGS_OBJECT_REQUIRED");
  }
  const result = Object.create(null);
  for (const [key, routeId] of Object.entries(bindings)) {
    if (!/^[a-zA-Z0-9._/-]{1,120}$/.test(key) || !routeSet.has(routeId)) {
      throw new Error("NOX_ROUTE_BINDING_NOT_IN_CANONICAL_ALLOWLIST");
    }
    result[key] = routeId;
  }
  return Object.freeze(result);
}

export function formatMetric(value, suffix = "%") {
  if (!safeNumber(value)) return "—";
  return String(Math.round(value * 10) / 10) + suffix;
}

export function buildSparkline(values, width = 320, height = 72) {
  if (!Array.isArray(values) || values.length < 2 || values.length > 240 ||
      !values.every(Number.isFinite)) return null;
  const min = Math.min(...values), max = Math.max(...values);
  const span = Math.max(1, max - min);
  return values.map((value, index) => {
    const x = (index / (values.length - 1)) * width;
    const y = height - ((value - min) / span) * (height - 8) - 4;
    return x.toFixed(1) + "," + y.toFixed(1);
  }).join(" ");
}

function setState(element, state, reason = "") {
  element.dataset.noxNativeState = state;
  if (reason) element.dataset.noxNativeReason = reason;
  else delete element.dataset.noxNativeReason;
  if (state !== "confirmed") {
    delete element.dataset.noxNativeAck;
    delete element.dataset.noxNativeRequestId;
  }
}

export function classifyNativeResponse(routeId, response) {
  if (!routeSet.has(routeId) || !response || response.routeId !== routeId) {
    return Object.freeze({state:"hold",reason:"NATIVE_ROUTE_CORRELATION_FAILED"});
  }
  if (response.state === "COMPLETED") {
    return Object.freeze({state:"confirmed",requestId:
      typeof response.requestId === "string" ? response.requestId : null});
  }
  if (["models.pull","models.retry","models.gguf.import"].includes(routeId) &&
      ["QUEUED","IN_PROGRESS"].includes(response.state)) {
    return Object.freeze({state:"queued",requestId:
      typeof response.requestId === "string" ? response.requestId : null});
  }
  if (response.state === "STOP_REQUESTED") {
    return Object.freeze({state:"stop_requested",requestId:
      typeof response.requestId === "string" ? response.requestId : null});
  }
  return Object.freeze({state:"hold",reason:
    typeof response.errorCode === "string" ? response.errorCode : "NATIVE_HANDLER_HOLD"});
}

function readActionPayload(element) {
  const raw = element.dataset.noxPayload;
  if (!raw) return {};
  if (raw.length > 4096) throw new Error("NOX_ACTION_PAYLOAD_TOO_LARGE");
  const value = JSON.parse(raw);
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("NOX_ACTION_PAYLOAD_OBJECT_REQUIRED");
  }
  return value;
}

function flattenNavigation(root) {
  for (const group of root.querySelectorAll("[data-nav-group]")) {
    const toggle = group.querySelector("[data-nav-toggle]");
    const submenu = group.querySelector(".nav-submenu");
    if (toggle) {
      toggle.removeAttribute("data-nav-toggle");
      toggle.setAttribute("aria-expanded", "true");
      toggle.hidden = true;
      toggle.tabIndex = -1;
    }
    if (submenu) {
      submenu.hidden = false;
      submenu.removeAttribute("aria-hidden");
      submenu.classList.add("nox-direct-action-grid");
      submenu.style.display = "grid";
    }
    group.classList.add("nox-expanded-nav-group");
  }
  for (const wrapper of root.querySelectorAll(".dd-wrap")) wrapper.remove();
}

function replaceSelects(root) {
  const documentRef = root.nodeType === 9 ? root : root.ownerDocument;
  if (!documentRef?.defaultView?.Event) throw new Error("NOX_DOCUMENT_EVENT_UNAVAILABLE");
  const EventCtor = documentRef.defaultView.Event;
  for (const select of root.querySelectorAll("select:not([data-nox-select-replaced])")) {
    const fieldset = documentRef.createElement("fieldset");
    fieldset.className = "nox-choice-group";
    fieldset.setAttribute("aria-label",
      select.labels && select.labels[0] ? select.labels[0].textContent.trim() :
      (select.getAttribute("aria-label") || "Выбор"));
    const options = Array.from(select.options).filter((option) =>
      !option.disabled && option.value !== "");
    if (!options.length) continue;
    const sync = () => {
      for (const button of fieldset.querySelectorAll("button")) {
        const option = select.options[Number(button.dataset.optionIndex)];
        const selected = !!(option && option.selected);
        button.setAttribute("aria-pressed", String(selected));
        button.classList.toggle("is-selected", selected);
      }
    };
    for (const option of options) {
      const button = documentRef.createElement("button");
      button.type = "button";
      button.className = "nox-choice-button";
      button.textContent = option.textContent.trim();
      button.dataset.optionIndex = String(option.index);
      button.addEventListener("click", () => {
        if (select.multiple) option.selected = !option.selected;
        else select.value = option.value;
        select.dispatchEvent(new EventCtor("change", { bubbles: true }));
        sync();
      });
      fieldset.append(button);
    }
    select.dataset.noxSelectReplaced = "true";
    select.classList.add("nox-visually-hidden-select");
    select.before(fieldset);
    sync();
  }
}

function guardUnboundControls(root) {
  const localSelectors = [
    "#themeToggle", "[data-drawer-open]", "[data-tab-target]",
    "[data-accordion-trigger]", ".nox-choice-button", "[data-nox-local-action]"
  ].join(",");
  for (const anchor of root.querySelectorAll("a[href]")) {
    const href = anchor.getAttribute("href") || "";
    const internalPage = /^(?!https?:|javascript:|#)([./][^:]*|[a-zA-Z0-9_-]+\\.html)(?:[?#].*)?$/.test(href);
    if (!internalPage && !anchor.dataset.noxRoute) {
      anchor.removeAttribute("href");
      anchor.setAttribute("aria-disabled", "true");
      anchor.dataset.noxNativeState = "hold";
      anchor.title = "Внешнее или демонстрационное действие отключено";
    }
  }
  for (const button of root.querySelectorAll("button:not([data-nox-route])")) {
    if (!button.matches(localSelectors)) {
      button.disabled = true;
      button.dataset.noxNativeState = "hold";
      button.title = "Действие не подключено к OneHost";
    }
  }
}

function createCosmicScene(root) {
  const doc = root.ownerDocument || root;
  const host = root.querySelector(".content") || root.querySelector("main") || root.body;
  if (!host || host.querySelector(".nox-cosmic-stage")) return () => {};
  const stage = doc.createElement("div");
  stage.className = "nox-cosmic-stage";
  stage.setAttribute("aria-hidden", "true");
  stage.innerHTML = `
    <div class="nox-cosmic-nebula"></div>
    <div class="nox-core-orb">
      <span class="nox-core-corona"></span><span class="nox-core-crust"></span>
      <span class="nox-core-lava"></span><span class="nox-core-glint"></span>
    </div>
    <div class="nox-orbit nox-orbit-a"><i></i></div>
    <div class="nox-orbit nox-orbit-b"><i></i></div>
    <div class="nox-orbit nox-orbit-c"><i></i></div>
    <div class="nox-cosmic-dust"></div>`;
  host.prepend(stage);
  return () => stage.remove();
}

function suppressDonorSamples(root) {
  // Adminator's showcase includes seeded analytics; never display those as NOX telemetry.
  const demoSelectors = [
    ".kpi-value", ".kpi-pill", ".kpi-compare", ".chart-meta-value",
    ".sv-region-value", ".sv-radial-chart .pct", ".stat-cell-value"
  ];
  for (const selector of demoSelectors) {
    for (const node of root.querySelectorAll(selector)) {
      node.textContent = "—";
      node.dataset.noxMetricState = "unavailable";
    }
  }
  const welcome = root.querySelector(".hero-sub");
  if (welcome) {
    welcome.textContent = "NOX HELION · показатели появятся после подключения подтверждённых данных OneHost.";
    welcome.dataset.noxDemoText = "removed";
  }
  const date = root.querySelector("#heroDate");
  if (date) date.textContent = "NOX HELION · LIVE SYSTEM";
  for (const canvas of root.querySelectorAll("canvas[data-chart-key]")) {
    const panel = root.createElement("div");
    panel.className = "nox-live-chart-placeholder";
    panel.dataset.noxSeries = canvas.dataset.chartKey;
    panel.dataset.noxSeriesState = "unavailable";
    panel.setAttribute("aria-label", "График ожидает подтверждённые данные OneHost");
    const svg = root.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", "0 0 320 72");
    svg.setAttribute("role", "img");
    svg.setAttribute("preserveAspectRatio", "none");
    const line = root.createElementNS(svgNS, "polyline");
    line.setAttribute("points", "0,36 320,36");
    line.setAttribute("class", "nox-live-chart-line");
    svg.append(line);
    const caption = root.createElement("span");
    caption.className = "nox-live-chart-caption";
    caption.textContent = "ОЖИДАНИЕ ДАННЫХ ONEHOST";
    panel.append(svg, caption);
    canvas.replaceWith(panel);
  }
}

function renderSnapshot(root, snapshot = {}) {
  const metrics = snapshot.metrics && typeof snapshot.metrics === "object" ? snapshot.metrics : {};
  for (const node of root.querySelectorAll("[data-nox-metric]")) {
    const value = metrics[node.dataset.noxMetric];
    node.textContent = formatMetric(value, node.dataset.suffix || "%");
    node.dataset.noxMetricState = safeNumber(value) ? "live" : "unavailable";
  }
  for (const node of root.querySelectorAll("[data-nox-series]")) {
    const values = snapshot.series && snapshot.series[node.dataset.noxSeries];
    const line = node.querySelector("polyline");
    const points = buildSparkline(values);
    if (!line || !points) {
      node.dataset.noxSeriesState = "unavailable";
      node.setAttribute("aria-label", "Нет подтверждённых данных");
    } else {
      line.setAttribute("points", points);
      node.dataset.noxSeriesState = "live";
      node.setAttribute("aria-label", "График с данными OneHost");
    }
  }
  root.documentElement.dataset.noxTelemetryAt =
    typeof snapshot.timestamp === "string" ? snapshot.timestamp : "unavailable";
}

export function mountAdminatorNox({
  root = document,
  nativeClient: suppliedNativeClient = null,
  routeBindings = globalThis.NOX_ADMINATOR_ROUTE_BINDINGS || {}
} = {}) {
  const doc = root.nodeType === 9 ? root : root.ownerDocument;
  if (!doc || !root.querySelectorAll) throw new TypeError("NOX_ADMINATOR_ROOT_REQUIRED");
  const bindings = validateRouteBindings(routeBindings);
  const view = doc.defaultView;
  const webview = view && view.chrome && view.chrome.webview;
  const nativeClient = suppliedNativeClient ||
    (webview ? createNativeMenuClient({webview,cryptoRef:view.crypto}) : null);

  flattenNavigation(root);
  replaceSelects(root);
  guardUnboundControls(root);
  const removeCosmicScene = createCosmicScene(root);
  suppressDonorSamples(root);

  let disposed = false;
  const onClick = async (event) => {
    const element = event.target && event.target.closest ?
      event.target.closest("[data-nox-route]") : null;
    if (!element || !root.contains(element)) return;
    event.preventDefault();
    if (disposed || element.dataset.noxPending === "true") return;
    const routeId = bindings[element.dataset.noxRoute];
    if (!routeId || !nativeClient) {
      setState(element, "hold", "NATIVE_HOST_OR_ROUTE_UNAVAILABLE");
      return;
    }
    element.dataset.noxPending = "true";
    setState(element, "pending");
    try {
      const payload = readActionPayload(element);
      const response = await nativeClient.request(routeId,payload);
      if (disposed) return;
      const state = classifyNativeResponse(routeId,response);
      setState(element,state.state,state.reason || "");
      if (state.requestId) element.dataset.noxNativeRequestId=state.requestId;
      if (state.state === "confirmed" || state.state === "queued" ||
          state.state === "stop_requested") {
        element.dataset.noxNativeAck = "true";
      }
    } catch (error) {
      if (!disposed) setState(element,"hold",
        error && typeof error.message === "string" &&
        /^[A-Z0-9_]{1,80}$/.test(error.message) ? error.message : "NATIVE_DISPATCH_FAILED");
    } finally {
      delete element.dataset.noxPending;
    }
  };

  const onTelemetry = (event) => {
    if (!disposed) renderSnapshot(root,event.detail || {});
  };
  root.addEventListener("click",onClick,true);
  if (view) view.addEventListener("nox:telemetry",onTelemetry);
  renderSnapshot(root,{metrics:{},series:{},timestamp:"unavailable"});

  return Object.freeze({
    renderSnapshot(snapshot) { if (!disposed) renderSnapshot(root,snapshot); },
    destroy() {
      if (disposed) return;
      disposed=true;
      root.removeEventListener("click",onClick,true);
      if (view) view.removeEventListener("nox:telemetry",onTelemetry);
      if (nativeClient && nativeClient !== suppliedNativeClient) nativeClient.destroy();
      removeCosmicScene();
    }
  });
}
