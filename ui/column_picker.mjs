// All matching is local: searching never changes a source name or sends a rerun.
export function normalizeName(value) {
  return String(value).normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}

export function filterColumns(options, search) {
  const terms = normalizeName(search).trim().split(/\s+/).filter(Boolean);
  return options.filter(option => {
    const name = normalizeName(option);
    return terms.every(term => name.includes(term));
  });
}

export function popupPlacement(rect, viewport, contentHeight) {
  const gutter = 12;
  const leftEdge = (viewport.offsetLeft ?? 0) + gutter;
  const topEdge = (viewport.offsetTop ?? 0) + gutter;
  const rightEdge = leftEdge + Math.max(0, viewport.width - 2 * gutter);
  const bottomEdge = topEdge + Math.max(0, viewport.height - 2 * gutter);
  const width = Math.min(Math.max(rect.width, 280), rightEdge - leftEdge);
  const below = Math.max(0, bottomEdge - Math.max(topEdge, rect.bottom + 6));
  const above = Math.max(0, Math.min(bottomEdge, rect.top - 6) - topEdge);
  const useAbove = below < 220 && above > below;
  // A phone keyboard can leave too little room on either side of the trigger.
  // Use the visible viewport in that case so search and a choice remain usable.
  const useViewport = Math.max(above, below) < 190;
  const maxHeight = Math.min(380, useViewport ? bottomEdge - topEdge : (useAbove ? above : below));
  const height = Math.min(contentHeight, maxHeight);
  const top = useViewport ? topEdge : (useAbove ? rect.top - height - 6 : rect.bottom + 6);
  return {
    width,
    maxHeight,
    left: Math.max(leftEdge, Math.min(rect.left, rightEdge - width)),
    top: Math.max(topEdge, Math.min(top, bottomEdge - height)),
  };
}

export default function({ parentElement, data, key, setTriggerValue }) {
  const root = parentElement.querySelector(".column-picker");
  // Streamlit can invoke this renderer repeatedly for new data without calling
  // the previous unmount cleanup. Retire the old bindings before recreating them.
  root.pickerCleanup?.();
  const label = root.querySelector(".field-label");
  const trigger = root.querySelector(".picker-trigger");
  const selectedLabel = root.querySelector(".selected-label");
  const popup = root.querySelector(".picker-popup");
  const input = root.querySelector(".search-input");
  const searchLabel = root.querySelector(".search-label");
  const list = root.querySelector(".option-list");
  const status = root.querySelector(".search-status");
  const id = `column-${key}`;
  let visible = [];
  let active = -1;
  const normalizedColumns = data.options.map(value => ({ value, name: normalizeName(value) }));

  label.textContent = data.label;
  label.htmlFor = `${id}-trigger`;
  trigger.id = `${id}-trigger`;
  trigger.setAttribute("aria-controls", `${id}-popup`);
  trigger.setAttribute("aria-label", `${data.label}: ${data.value}. Choose column`);
  selectedLabel.textContent = data.value;
  trigger.title = data.value;
  popup.id = `${id}-popup`;
  popup.setAttribute("aria-label", `Choose column for ${data.label}`);
  input.id = `${id}-search`;
  searchLabel.htmlFor = input.id;
  input.setAttribute("aria-label", `Search columns for ${data.label}`);
  input.setAttribute("aria-controls", `${id}-options`);
  list.id = `${id}-options`;
  list.setAttribute("aria-label", data.label);

  function isOpen() { return popup.matches(":popover-open"); }

  function position() {
    if (!isOpen()) return;
    const rect = trigger.getBoundingClientRect();
    const viewport = window.visualViewport ?? { width: window.innerWidth, height: window.innerHeight };
    const placement = popupPlacement(rect, viewport, popup.scrollHeight);
    for (const property of ["width", "maxHeight", "left", "top"]) {
      popup.style[property] = `${placement[property]}px`;
    }
  }

  function markActive(scroll = false) {
    const nodes = list.querySelectorAll(".column-option");
    for (let i = 0; i < nodes.length; i++) nodes[i].dataset.active = String(i === active);
    const current = nodes[active];
    if (current) {
      input.setAttribute("aria-activedescendant", current.id);
      if (scroll) current.scrollIntoView({ block: "nearest" });
    } else input.removeAttribute("aria-activedescendant");
  }

  function close(restoreFocus = false) {
    if (isOpen()) popup.hidePopover();
    trigger.setAttribute("aria-expanded", "false");
    if (restoreFocus) trigger.focus({ preventScroll: true });
  }

  function choose(value) {
    selectedLabel.textContent = value;
    trigger.setAttribute("aria-label", `${data.label}: ${value}. Choose column`);
    trigger.title = value;
    close(true);
    if (value !== data.value) setTriggerValue("selected", value);
  }

  function renderOptions(preferSelected = false) {
    const terms = normalizeName(input.value).trim().split(/\s+/).filter(Boolean);
    visible = normalizedColumns.filter(option => terms.every(term => option.name.includes(term)))
      .map(option => option.value);
    active = visible.length ? (preferSelected ? Math.max(0, visible.indexOf(data.value)) : 0) : -1;
    list.replaceChildren();
    visible.forEach((value, index) => {
      const option = document.createElement("div");
      option.className = "column-option";
      option.id = `${id}-option-${index}`;
      option.setAttribute("role", "option");
      option.setAttribute("aria-selected", String(value === data.value));
      const text = document.createElement("span");
      text.textContent = value;
      option.append(text);
      if (value === data.value) {
        const mark = document.createElement("span");
        mark.className = "selection-mark";
        mark.setAttribute("aria-hidden", "true");
        mark.textContent = "✓";
        option.append(mark);
      }
      option.onpointerdown = event => event.preventDefault();
      option.onpointermove = () => { active = index; markActive(); };
      option.onclick = () => choose(value);
      list.append(option);
    });
    status.textContent = visible.length ? `${visible.length} column${visible.length === 1 ? "" : "s"}. Use arrow keys and Enter to choose.` : "No columns match. Your current selection is unchanged.";
    markActive();
    position();
  }

  function open() {
    if (isOpen()) return;
    input.value = "";
    renderOptions(true);
    popup.showPopover();
    trigger.setAttribute("aria-expanded", "true");
    position();
    input.focus({ preventScroll: true });
    markActive(true);
  }

  trigger.onclick = () => isOpen() ? close(true) : open();
  trigger.onkeydown = event => {
    if (["ArrowDown", "ArrowUp"].includes(event.key)) {
      event.preventDefault();
      open();
    }
  };
  input.oninput = () => renderOptions();
  input.onkeydown = event => {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      close(true);
    } else if (["ArrowDown", "ArrowUp"].includes(event.key)) {
      event.preventDefault();
      if (!visible.length) return;
      active = (active + (event.key === "ArrowDown" ? 1 : -1) + visible.length) % visible.length;
      markActive(true);
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (active >= 0) choose(visible[active]);
    } else if (event.key === "Tab") close();
  };
  popup.ontoggle = () => trigger.setAttribute("aria-expanded", String(isOpen()));

  // Native top-layer popovers escape column clipping without touching Streamlit's
  // DOM. Reposition only while open, including when a phone keyboard appears.
  window.addEventListener("resize", position);
  window.addEventListener("scroll", position, true);
  window.visualViewport?.addEventListener("resize", position);
  window.visualViewport?.addEventListener("scroll", position);
  const restoreFocus = root.dataset.restoreFocus === "true";
  if (restoreFocus) {
    delete root.dataset.restoreFocus;
    trigger.focus({ preventScroll: true });
  }
  let cleaned = false;
  const cleanup = () => {
    if (cleaned) return;
    cleaned = true;
    root.dataset.restoreFocus = String(trigger.matches(":focus"));
    window.removeEventListener("resize", position);
    window.removeEventListener("scroll", position, true);
    window.visualViewport?.removeEventListener("resize", position);
    window.visualViewport?.removeEventListener("scroll", position);
    close();
  };
  root.pickerCleanup = cleanup;
  return () => {
    // An old asynchronous mount may finish after a newer render. Only retire
    // its own bindings and leave the current instance's cleanup reference alone.
    cleanup();
    if (root.pickerCleanup === cleanup) delete root.pickerCleanup;
  };
}
