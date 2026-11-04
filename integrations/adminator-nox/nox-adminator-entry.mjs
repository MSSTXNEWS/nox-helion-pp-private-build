import { mountAdminatorNox } from "./nox-adminator-adapter.mjs";

const mount = () => {
  if (document.documentElement.dataset.noxAdminatorMounted === "true") return;
  document.documentElement.dataset.noxAdminatorMounted = "true";
  try {
    const adapter = mountAdminatorNox({ root: document });
    window.NOX_ADMINATOR_UI = Object.freeze({
      updateTelemetry: (snapshot) => adapter.renderSnapshot(snapshot),
      dispose: () => adapter.destroy()
    });
    window.addEventListener("pagehide", () => adapter.destroy(), { once: true });
  } catch (error) {
    document.documentElement.dataset.noxAdminatorMount = "hold";
    console.error("NOX_ADMINATOR_MOUNT_HOLD", error && error.message || "UNKNOWN");
  }
};
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount, { once: true });
} else {
  mount();
}
