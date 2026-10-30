import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const src = fileURLToPath(new URL(".", import.meta.url));
const filesUnder = (directory) => readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
  const path = join(directory, entry.name);
  return entry.isDirectory() ? filesUnder(path) : [path];
});

test("production styles and components use design tokens instead of raw color literals", () => {
  const styles = filesUnder(src).filter((path) =>
    (path.endsWith(".css") && !path.endsWith("/tokens.css")) || path.endsWith(".tsx"),
  );
  const literalColor = /#[\da-f]{3,8}\b|rgba?\s*\(/i;
  const violations = styles.flatMap((path) => {
    const content = readFileSync(path, "utf8");
    return content.split("\n").flatMap((line, index) => literalColor.test(line)
      ? [`${relative(src, path)}:${index + 1}`]
      : []);
  });
  assert.deepEqual(violations, []);
});

test("shared tokens define separate UI and chart color roles", () => {
  const tokens = readFileSync(join(src, "shared/styles/tokens.css"), "utf8");
  for (const token of ["--surface:", "--content-primary:", "--border:", "--accent:", "--chart-primary:", "--chart-status-warning:", "--chart-grid:"]) {
    assert.ok(tokens.includes(token), `Missing design token ${token}`);
  }
});
