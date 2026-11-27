import { PATTERNS, TA } from "./ta";

/**
 * Tamil for the whole page: while Tamil is on, every text node and every label attribute (aria-label, placeholder,
 * title) whose English is in the Tamil table (or matches a pattern) is shown in Tamil; the English is kept and put
 * back when English is chosen again. React keeps rendering English, and a MutationObserver translates whatever it
 * renders next, so screens loaded later are covered too. Text inside [data-no-translate] (numbers typed by the
 * user, document previews) is left alone.
 */
const ATTRS = ["aria-label", "placeholder", "title"] as const;
const originalText = new WeakMap<Text, string>();
const originalAttr = new WeakMap<Element, Map<string, string>>();
let observer: MutationObserver | null = null;
let busy = false;

export function toTamil(english: string): string | null {
  const core = english.trim();
  if (!core || !/[A-Za-z]/.test(core)) return null;
  const hit = TA[core];
  let out: string | null = hit ?? null;
  if (out === null) {
    for (const [re, build] of PATTERNS) {
      const m = core.match(re);
      if (m) {
        out = build(...m);
        break;
      }
    }
  }
  if (out === null || out === core) return null;
  const lead = english.match(/^\s*/)?.[0] ?? "";
  const trail = english.match(/\s*$/)?.[0] ?? "";
  return `${lead}${out}${trail}`;
}

function skip(el: Element | null): boolean {
  return !el || !!el.closest("script,style,textarea,[data-no-translate]");
}

function translateText(node: Text) {
  if (skip(node.parentElement)) return;
  const current = node.nodeValue ?? "";
  const known = originalText.get(node);
  // React may have written new English into the node since we translated it.
  const english = known !== undefined && toTamil(known) === current ? known : current;
  const ta = toTamil(english);
  if (ta === null) return;
  originalText.set(node, english);
  if (node.nodeValue !== ta) node.nodeValue = ta;
}

function translateAttrs(el: Element) {
  if (skip(el)) return;
  for (const a of ATTRS) {
    const v = el.getAttribute(a);
    if (!v) continue;
    const saved = originalAttr.get(el)?.get(a);
    const english = saved !== undefined && toTamil(saved) === v ? saved : v;
    const ta = toTamil(english);
    if (ta === null) continue;
    if (!originalAttr.has(el)) originalAttr.set(el, new Map());
    originalAttr.get(el)!.set(a, english);
    if (v !== ta) el.setAttribute(a, ta);
  }
}

function walk(root: Node) {
  if (root.nodeType === Node.TEXT_NODE) {
    translateText(root as Text);
    return;
  }
  if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_NODE) return;
  const el = root as Element;
  if (el.nodeType === Node.ELEMENT_NODE) translateAttrs(el);
  const texts = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let t: Node | null;
  while ((t = texts.nextNode())) translateText(t as Text);
  if (el.querySelectorAll)
    el.querySelectorAll("[aria-label],[placeholder],[title]").forEach(translateAttrs);
}

function restore(root: Node) {
  const texts = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let t: Node | null;
  while ((t = texts.nextNode())) {
    const node = t as Text;
    const english = originalText.get(node);
    if (english !== undefined && toTamil(english) === node.nodeValue) node.nodeValue = english;
    originalText.delete(node);
  }
  (root as Element).querySelectorAll?.("[aria-label],[placeholder],[title]").forEach((el) => {
    const saved = originalAttr.get(el);
    saved?.forEach((english, a) => {
      if (toTamil(english) === el.getAttribute(a)) el.setAttribute(a, english);
    });
    originalAttr.delete(el);
  });
}

export function startTamil() {
  if (observer || typeof document === "undefined") return;
  walk(document.body);
  observer = new MutationObserver((records) => {
    if (busy) return;
    busy = true;
    try {
      for (const r of records) {
        if (r.type === "characterData") translateText(r.target as Text);
        else if (r.type === "attributes") translateAttrs(r.target as Element);
        else r.addedNodes.forEach(walk);
      }
    } finally {
      busy = false;
    }
  });
  observer.observe(document.body, {
    subtree: true,
    childList: true,
    characterData: true,
    attributes: true,
    attributeFilter: [...ATTRS],
  });
}

export function stopTamil() {
  observer?.disconnect();
  observer = null;
  if (typeof document !== "undefined") restore(document.body);
}
