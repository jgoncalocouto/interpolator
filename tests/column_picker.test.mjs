// Run with: node --test tests/column_picker.test.mjs
import assert from "node:assert/strict";
import test from "node:test";
import renderPicker, { filterColumns, popupPlacement } from "../ui/column_picker.mjs";

test("column search folds accents and case without changing original labels", () => {
  const options = ["Énergie totale (J)", "Température (°C)", "Time (s)"];
  assert.deepEqual(filterColumns(options, "ENERGIE"), ["Énergie totale (J)"]);
  assert.deepEqual(filterColumns(options, "perature"), ["Température (°C)"]);
  assert.deepEqual(options, ["Énergie totale (J)", "Température (°C)", "Time (s)"]);
});

test("every search term must occur, in any order", () => {
  const options = ["Mean air température (°C)", "Mean ground température", "Air pressure"];
  assert.deepEqual(filterColumns(options, "temp mean air"), [options[0]]);
  assert.deepEqual(filterColumns(options, "  MEAN\tTEMPERATURE  "), options.slice(0, 2));
  assert.deepEqual(filterColumns(options, "air ground"), []);
});

test("empty search returns all columns in source order, including Unicode", () => {
  const options = ["測定値", "β", "Z", "A"];
  assert.deepEqual(filterColumns(options, "\n  "), options);
  assert.deepEqual(filterColumns(options, "測"), ["測定値"]);
  assert.deepEqual(filterColumns(options, "missing"), []);
});

test("picker popup stays within a 390px viewport near either screen edge", () => {
  const viewport = { width: 390, height: 844 };
  for (const top of [16, 400, 760]) {
    const result = popupPlacement({ left: 280, width: 90, top, bottom: top + 44 }, viewport, 500);
    assert.ok(result.left >= 12);
    assert.ok(result.left + result.width <= 378);
    assert.ok(result.top >= 12);
    assert.ok(result.top + result.maxHeight <= 832);
  }
});

test("phone keyboard and visual viewport offsets constrain popup height", () => {
  const viewport = { width: 390, height: 260, offsetTop: 320, offsetLeft: 0 };
  const result = popupPlacement({ left: 16, width: 358, top: 430, bottom: 474 }, viewport, 500);
  assert.ok(result.top >= 332);
  assert.ok(result.top + result.maxHeight <= 568);
  assert.ok(result.maxHeight >= 190, "use available viewport when neither side can fit search and choices");
});

test("data rerenders retain trigger focus without accumulating window listeners", () => {
  function eventTarget() {
    const listeners = new Map();
    return {
      listeners,
      addEventListener(name, handler) {
        if (!listeners.has(name)) listeners.set(name, new Set());
        listeners.get(name).add(handler);
      },
      removeEventListener(name, handler) { listeners.get(name)?.delete(handler); },
    };
  }
  function element() {
    return { dataset: {}, style: {}, setAttribute() {}, matches: () => false };
  }
  const children = Object.fromEntries([
    ".field-label", ".picker-trigger", ".selected-label", ".picker-popup",
    ".search-input", ".search-label", ".option-list", ".search-status",
  ].map(name => [name, element()]));
  const root = { dataset: {}, querySelector: selector => children[selector] };
  const trigger = children[".picker-trigger"];
  let focused = false;
  let restored = 0;
  trigger.matches = selector => selector === ":focus" && focused;
  trigger.focus = () => { focused = true; restored++; };
  const previousWindow = globalThis.window;
  globalThis.window = { ...eventTarget(), visualViewport: eventTarget() };
  try {
    const args = { parentElement: { querySelector: () => root }, key: "x",
      data: { label: "X", value: "Time", options: ["Time", "Reading"] }, setTriggerValue() {} };
    const cleanupFirst = renderPicker(args);
    focused = true; // A chosen value closes the popup and returns to its trigger.
    const cleanupSecond = renderPicker({ ...args, data: { ...args.data, value: "Reading" } });
    assert.equal(restored, 1);
    assert.equal(window.listeners.get("resize").size, 1);
    assert.equal(window.listeners.get("scroll").size, 1);
    assert.equal(window.visualViewport.listeners.get("resize").size, 1);
    assert.equal(window.visualViewport.listeners.get("scroll").size, 1);
    cleanupFirst(); // A late disposal cannot retire a newer render.
    assert.equal(window.listeners.get("resize").size, 1);
    cleanupSecond();
    assert.equal(window.listeners.get("resize").size, 0);
    assert.equal(window.visualViewport.listeners.get("scroll").size, 0);
  } finally {
    globalThis.window = previousWindow;
  }
});

test("keyboard search chooses a matching source and Escape preserves the current choice", () => {
  let focused = null;
  function element() {
    return {
      children: [], dataset: {}, style: {}, attributes: {}, scrollHeight: 300,
      setAttribute(name, value) { this.attributes[name] = value; },
      removeAttribute(name) { delete this.attributes[name]; },
      append(child) { this.children.push(child); },
      replaceChildren() { this.children = []; },
      querySelectorAll() { return this.children; },
      matches(selector) { return selector === ":popover-open" ? Boolean(this.open) : focused === this; },
      showPopover() { this.open = true; },
      hidePopover() { this.open = false; },
      focus() { focused = this; },
      scrollIntoView() {},
      getBoundingClientRect() { return { left: 16, top: 160, bottom: 204, width: 358 }; },
    };
  }
  const children = Object.fromEntries([
    ".field-label", ".picker-trigger", ".selected-label", ".picker-popup",
    ".search-input", ".search-label", ".option-list", ".search-status",
  ].map(name => [name, element()]));
  const root = { dataset: {}, querySelector: selector => children[selector] };
  const previousWindow = globalThis.window;
  const previousDocument = globalThis.document;
  globalThis.window = { innerWidth: 390, innerHeight: 844, addEventListener() {}, removeEventListener() {} };
  globalThis.document = { createElement: element };
  const events = [];
  const keyEvent = key => ({ key, preventDefault() {}, stopPropagation() {} });
  let cleanup;
  try {
    cleanup = renderPicker({ parentElement: { querySelector: () => root }, key: "x",
      data: { label: "X", value: "Time", options: ["Time", "Énergie totale (J)", "Reading"] },
      setTriggerValue: (name, value) => events.push([name, value]) });
    const trigger = children[".picker-trigger"];
    const input = children[".search-input"];
    const popup = children[".picker-popup"];
    trigger.onkeydown(keyEvent("ArrowDown"));
    assert.equal(popup.open, true);
    assert.equal(focused, input);
    input.onkeydown(keyEvent("ArrowDown"));
    assert.match(input.attributes["aria-activedescendant"], /option-1$/);
    input.onkeydown(keyEvent("ArrowUp"));
    assert.match(input.attributes["aria-activedescendant"], /option-0$/);
    input.value = "tot energie";
    input.oninput();
    assert.equal(children[".option-list"].children.length, 1);
    input.onkeydown(keyEvent("Enter"));
    assert.equal(popup.open, false);
    assert.equal(focused, trigger);
    assert.deepEqual(events, [["selected", "Énergie totale (J)"]]);

    trigger.onclick();
    input.value = "no match";
    input.oninput();
    input.onkeydown(keyEvent("Enter"));
    assert.match(children[".search-status"].textContent, /No columns match/);
    assert.equal(events.length, 1);
    input.onkeydown(keyEvent("Escape"));
    assert.equal(popup.open, false);
    assert.equal(focused, trigger);
    assert.equal(events.length, 1);
  } finally {
    cleanup?.();
    globalThis.window = previousWindow;
    globalThis.document = previousDocument;
  }
});
