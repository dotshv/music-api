// Shared behaviour: mobile nav, code tabs and copy buttons.
(function () {
  // ---- Mobile navigation
  const toggle = document.getElementById("navToggle");
  const nav = document.getElementById("siteNav");
  if (toggle && nav) {
    const setOpen = (open) => {
      nav.classList.toggle("is-open", open);
      toggle.setAttribute("aria-expanded", String(open));
    };
    toggle.addEventListener("click", () => setOpen(!nav.classList.contains("is-open")));
    nav.addEventListener("click", (e) => {
      if (e.target.closest("a")) setOpen(false);
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") setOpen(false);
    });
  }

  // ---- Code tabs
  document.querySelectorAll("[data-tabs]").forEach((root) => {
    const tabs = [...root.querySelectorAll('[role="tab"]')];

    function select(tab) {
      tabs.forEach((t) => {
        const on = t === tab;
        t.setAttribute("aria-selected", String(on));
        t.tabIndex = on ? 0 : -1;
        document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
      });
      tab.focus();
    }

    tabs.forEach((tab, i) => {
      tab.addEventListener("click", () => select(tab));
      tab.addEventListener("keydown", (e) => {
        const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
        if (step) {
          e.preventDefault();
          select(tabs[(i + step + tabs.length) % tabs.length]);
        }
      });
    });
  });

  // ---- Copy buttons: <button data-copy="#selector">
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-copy]");
    if (!btn) return;
    const source = document.querySelector(btn.dataset.copy);
    if (!source) return;

    const original = btn.getAttribute("aria-label");
    try {
      await navigator.clipboard.writeText(source.textContent.trim());
      btn.classList.add("is-copied");
      btn.setAttribute("aria-label", "Copied");
    } catch {
      btn.setAttribute("aria-label", "Copy failed");
    }
    setTimeout(() => {
      btn.classList.remove("is-copied");
      btn.setAttribute("aria-label", original);
    }, 1800);
  });
})();
