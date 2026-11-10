/**
 * Client mirror of backend `applications/answers.py` visibility rules, used to show conditional
 * questions instantly. The server re-evaluates and discards hidden answers, so this is UX only.
 */
export interface ShowIf {
  question?: string;
  op?: string;
  value?: unknown;
}

export interface VisQuestion {
  key: string;
  branching?: { show_if?: ShowIf } | Record<string, unknown>;
}

const empty = (v: unknown) =>
  v === null || v === undefined || v === "" || (Array.isArray(v) && v.length === 0);

function matches(op: string, answer: unknown, expected: unknown): boolean {
  if (op === "answered") return !empty(answer);
  if (empty(answer)) return false;
  const values = (Array.isArray(answer) ? answer : [answer]).map(String);
  const wanted = (Array.isArray(expected) ? expected : [expected]).map(String);
  if (op === "eq" || op === "in") return values.some((v) => wanted.includes(v));
  if (op === "neq" || op === "not_in") return values.every((v) => !wanted.includes(v));
  const a = Number(answer);
  const e = Number(expected);
  if (Number.isNaN(a) || Number.isNaN(e)) return false;
  return op === "gte" ? a >= e : op === "lte" ? a <= e : false;
}

export function visibleKeys(questions: VisQuestion[], answers: Record<string, unknown>): string[] {
  const shown: string[] = [];
  for (const q of questions) {
    const showIf = (q.branching as { show_if?: ShowIf } | undefined)?.show_if;
    if (showIf) {
      const parent = String(showIf.question ?? "");
      if (
        !shown.includes(parent) ||
        !matches(String(showIf.op ?? "eq"), answers[parent], showIf.value)
      )
        continue;
    }
    shown.push(q.key);
  }
  return shown;
}

export function wordCount(text: string): number {
  return text.trim() ? text.trim().split(/\s+/).length : 0;
}
