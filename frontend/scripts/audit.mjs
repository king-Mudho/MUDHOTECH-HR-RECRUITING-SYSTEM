#!/usr/bin/env node
/**
 * Production dependency audit gate (CI): fails on high/critical advisories unless an advisory is
 * listed in audit-allowlist.json with a reason and a review date that has not passed.
 * An expired entry fails the build again, so accepted risks are re-examined.
 */
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

const SEVERE = new Set(["high", "critical"]);
const allowlist = JSON.parse(readFileSync(new URL("../audit-allowlist.json", import.meta.url)));
const today = new Date().toISOString().slice(0, 10);

let raw;
try {
  raw = execFileSync("npm", ["audit", "--omit=dev", "--json"], {
    encoding: "utf8",
    shell: process.platform === "win32",
  });
} catch (err) {
  raw = err.stdout; // npm audit exits non-zero when it finds anything
}
const report = JSON.parse(raw);

const findings = [];
for (const [name, vuln] of Object.entries(report.vulnerabilities ?? {})) {
  for (const via of vuln.via) {
    if (typeof via !== "object" || !SEVERE.has(via.severity)) continue;
    const id = via.url?.split("/").pop() ?? via.source;
    findings.push({ name, id, severity: via.severity, title: via.title });
  }
}

const failures = [];
for (const f of findings) {
  const entry = allowlist.find((a) => a.id === f.id);
  if (!entry) failures.push(`${f.severity} ${f.id} in ${f.name}: ${f.title}`);
  else if (entry.reviewBy < today)
    failures.push(`${f.id} allowlist entry expired on ${entry.reviewBy}`);
  else console.log(`accepted ${f.id} (${f.name}) until ${entry.reviewBy}: ${entry.reason}`);
}
if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}
console.log(`npm audit: no unaccepted high/critical advisories (${findings.length} accepted).`);
