#!/usr/bin/env node
/**
 * Generate `src/types/api.d.ts` from the backend OpenAPI schema (never hand-edit the output).
 *
 * Source (first match): `API_SCHEMA` env (file path or URL) -> ../backend/schema.yml
 * -> http://127.0.0.1:8000/api/schema/.
 */
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const candidates = [
  process.env.API_SCHEMA,
  resolve(root, "../backend/schema.yml"),
  "http://127.0.0.1:8000/api/schema/",
].filter(Boolean);
const source = candidates.find((c) => c.startsWith("http") || existsSync(c));
const output = resolve(root, "src/types/api.d.ts");

console.log(`gen:api  ${source}  ->  ${output}`);
execFileSync(
  process.execPath,
  [resolve(root, "node_modules/openapi-typescript/bin/cli.js"), source, "-o", output],
  { stdio: "inherit" },
);
