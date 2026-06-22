import assert from "node:assert/strict";
import { test } from "node:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";

const repoRoot = path.resolve(import.meta.dirname, "..");
const sourcePath = path.join(repoRoot, "app", "lib", "auditFormat.ts");
const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "topoaudit-audit-fmt-"));
const compiledPath = path.join(tempDir, "auditFormat.js");

execFileSync(
  path.join(repoRoot, "node_modules", ".bin", "tsc"),
  [sourcePath, "--target", "ES2020", "--module", "NodeNext", "--moduleResolution", "NodeNext", "--types", "node", "--skipLibCheck", "--outDir", tempDir],
  { cwd: repoRoot, stdio: "inherit" },
);

const fmt = await import(compiledPath);

test("extraction_score null s'affiche 'à valider' (pas 0/100)", () => {
  assert.equal(fmt.extractionScoreText(null, "fr"), "À valider");
  assert.equal(fmt.extractionScoreText(undefined, "fr"), "À valider");
  assert.equal(fmt.extractionScoreText(null, "en"), "To validate");
  assert.ok(fmt.isExtractionScoreNull(null));
  assert.ok(fmt.isExtractionScoreNull(undefined));
});

test("un score réel (y compris 0) reste numérique, pas converti", () => {
  assert.equal(fmt.extractionScoreText(0, "fr"), "0/100");
  assert.equal(fmt.extractionScoreText(85, "fr"), "85/100");
  assert.ok(!fmt.isExtractionScoreNull(0));
  assert.ok(!fmt.isExtractionScoreNull(85));
});
