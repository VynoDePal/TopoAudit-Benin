import assert from "node:assert/strict";
import { test } from "node:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";

const repoRoot = path.resolve(import.meta.dirname, "..");
const sourcePath = path.join(repoRoot, "app", "components", "resultsReportShared.ts");
const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "topoaudit-web-test-"));
const compiledPath = path.join(tempDir, "resultsReportShared.js");

execFileSync(
  path.join(repoRoot, "node_modules", ".bin", "tsc"),
  [
    sourcePath,
    "--target", "ES2020",
    "--module", "NodeNext",
    "--moduleResolution", "NodeNext",
    "--types", "node",
    "--skipLibCheck",
    "--outDir", tempDir
  ],
  { cwd: repoRoot, stdio: "inherit" }
);

const shared = await import(compiledPath);

test("dashboard demo audit reuses audited moderate report conventions", () => {
  assert.equal(shared.demoAudit.state, "AUDITED");
  assert.equal(shared.demoAudit.risk_level, "moderate");
  assert.equal(shared.riskLabels[shared.demoAudit.risk_level], "Modéré");
  assert.equal(shared.reportFilename(shared.demoAudit.project_id), "topoaudit-demo-cotonou-001-report.pdf");
});

test("score and risk tones cover low, moderate and high cases", () => {
  assert.equal(shared.scoreTone(96), "good");
  assert.equal(shared.scoreTone(74), "warning");
  assert.equal(shared.scoreTone(48), "danger");
  assert.equal(shared.riskTone("low"), "good");
  assert.equal(shared.riskTone("moderate"), "warning");
  assert.equal(shared.riskTone("high"), "danger");
});

test("dashboard parcel fixture is closed WGS84 GeoJSON", () => {
  const ring = shared.dashboardParcels.features[0].geometry.coordinates[0];
  assert.deepEqual(ring[0], ring.at(-1));
  assert.ok(ring.every(([longitude, latitude]) => longitude >= 0 && longitude <= 4 && latitude >= 5 && latitude <= 13));
});
