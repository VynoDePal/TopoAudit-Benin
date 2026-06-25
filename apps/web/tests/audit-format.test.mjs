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

test("extractionDisplay : score OCR machine présent → X/100 (pas validé)", () => {
  const d = fmt.extractionDisplay(85, null, "fr");
  assert.equal(d.label, "85/100");
  assert.equal(d.validated, false);
  assert.equal(d.nullScore, false);
  assert.equal(d.gaugeScore, 85);
});

test("extractionDisplay : pas de score OCR mais bornes cochées → « Validé · X/100 »", () => {
  const d = fmt.extractionDisplay(null, 100, "fr");
  assert.equal(d.label, "Validé · 100/100");
  assert.equal(d.validated, true);
  assert.equal(d.nullScore, false);
  assert.equal(d.gaugeScore, 100);
  // validation partielle
  const partial = fmt.extractionDisplay(null, 73, "fr");
  assert.equal(partial.label, "Validé · 73/100");
  assert.equal(partial.gaugeScore, 73);
});

test("extractionDisplay : ni OCR ni validation → « À valider »", () => {
  const d = fmt.extractionDisplay(null, null, "fr");
  assert.equal(d.label, "À valider");
  assert.equal(d.validated, false);
  assert.equal(d.nullScore, true);
  assert.equal(d.gaugeScore, null);
});
