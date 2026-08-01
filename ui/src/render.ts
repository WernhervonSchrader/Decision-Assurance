export function text(tag: keyof HTMLElementTagNameMap, value: unknown, className?: string): HTMLElement {
  const element = document.createElement(tag);
  element.textContent = typeof value === "string" ? value : JSON.stringify(value);
  if (className) element.className = className;
  return element;
}

export function renderExternalContent(target: HTMLElement, values: unknown[]): void {
  target.replaceChildren();
  for (const value of values) {
    const item = document.createElement("article");
    item.className = "external-source";
    item.append(text("pre", value));
    target.append(item);
  }
}

export function neverComputesGovernanceOutcome(value: unknown): string {
  if (typeof value !== "string" || !["PASS", "REVIEW", "BLOCK"].includes(value)) return "UNAVAILABLE";
  return value;
}
