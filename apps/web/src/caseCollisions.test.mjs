import test from "node:test";
import assert from "node:assert/strict";
import { readdirSync } from "node:fs";
import { extname, basename, join } from "node:path";

// В Windows имена файлов не различают регистр: «./Scheme» может открыть
// scheme.mjs вместо Scheme.tsx. Модули в одной папке не должны отличаться
// только регистром или расширением.
const modules = new Set([".mjs", ".js", ".mts", ".ts", ".jsx", ".tsx", ".json"]);

function walk(directory, found = []) {
  const names = new Map();
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) { walk(path, found); continue; }
    if (!modules.has(extname(entry.name))) continue;
    const key = basename(entry.name, extname(entry.name)).toLowerCase();
    if (names.has(key)) found.push(`${names.get(key)} ↔ ${path}`);
    else names.set(key, path);
  }
  return found;
}

test("module names differ by more than case, so imports resolve the same on Windows", () => {
  assert.deepEqual(walk(new URL(".", import.meta.url).pathname), []);
});
