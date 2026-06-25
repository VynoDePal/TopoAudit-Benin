import assert from "node:assert/strict";
import { test } from "node:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";

const repoRoot = path.resolve(import.meta.dirname, "..");
const sourcePath = path.join(repoRoot, "app", "lib", "territoryClient.ts");
const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "topoaudit-territory-"));
const compiledPath = path.join(tempDir, "territoryClient.js");

execFileSync(
  path.join(repoRoot, "node_modules", ".bin", "tsc"),
  [sourcePath, "--target", "ES2020", "--module", "NodeNext", "--moduleResolution", "NodeNext", "--skipLibCheck", "--outDir", tempDir],
  { cwd: repoRoot, stdio: "inherit" },
);

const m = await import(compiledPath);

test("CRS transformable + outside_benin → badge rouge (critical)", () => {
  const badge = m.territoryBadge("outside_benin", "fr");
  assert.equal(badge.tone, "critical");
  assert.match(badge.label, /Hors Bénin/);
  assert.equal(m.blocksAudit("outside_benin"), true);
});

test("inside_benin → badge OK (vert)", () => {
  const badge = m.territoryBadge("inside_benin", "fr");
  assert.equal(badge.tone, "ok");
  assert.match(badge.label, /territoire béninois/);
  assert.equal(m.blocksAudit("inside_benin"), false);
});

test("LOCAL_ONLY → contrôle impossible (neutre, n'avertit pas avant audit)", () => {
  const badge = m.territoryBadge("not_applicable_local_crs", "fr");
  assert.equal(badge.tone, "neutral");
  assert.match(badge.label, /impossible sans géoréférencement/);
  assert.equal(m.blocksAudit("not_applicable_local_crs"), false);
});

test("near_border_partial → avertissement (warn), ne bloque pas comme hors Bénin", () => {
  const badge = m.territoryBadge("near_border_partial", "fr");
  assert.equal(badge.tone, "warn");
  assert.equal(m.blocksAudit("near_border_partial"), false);
});

test("territoryCheckBody : bornes valides → coordonnées numériques + CRS ; ignore les vides", () => {
  const body = m.territoryCheckBody(
    [
      { x: "403825,84", y: "707630.38" }, // virgule décimale tolérée
      { x: "403836.57", y: "707626.36" },
      { x: "", y: "707641.10" }, // borne incomplète → ignorée
      { x: "403840.12", y: "707641.10" },
    ],
    "EPSG:32631",
  );
  assert.equal(body.source_crs, "EPSG:32631");
  assert.equal(body.coordinates.length, 3); // la borne vide est exclue
  assert.deepEqual(body.coordinates[0], [403825.84, 707630.38]);
});
