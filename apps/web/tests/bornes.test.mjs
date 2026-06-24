import assert from "node:assert/strict";
import { test } from "node:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";

const repoRoot = path.resolve(import.meta.dirname, "..");
const sourcePath = path.join(repoRoot, "app", "lib", "bornes.ts");
const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "topoaudit-bornes-"));
const compiledPath = path.join(tempDir, "bornes.js");

execFileSync(
  path.join(repoRoot, "node_modules", ".bin", "tsc"),
  [sourcePath, "--target", "ES2020", "--module", "NodeNext", "--moduleResolution", "NodeNext", "--types", "node", "--skipLibCheck", "--outDir", tempDir],
  { cwd: repoRoot, stdio: "inherit" },
);

const b = await import(compiledPath);

test("confidence=null/undefined affiche 'À valider' (jamais 0%)", () => {
  assert.equal(b.confidenceLabel(null, "fr"), "À valider");
  assert.equal(b.confidenceLabel(undefined, "fr"), "À valider");
  assert.equal(b.confidenceLabel(null, "en"), "To validate");
});

test("confidence=0 (vraie valeur) affiche '0%'", () => {
  assert.equal(b.confidenceLabel(0, "fr"), "0%");
  assert.equal(b.confidenceLabel(0.85, "fr"), "85%");
});

test("modification d'une coordonnée repasse validated à false", () => {
  const pt = { label: "B1", x: "100", y: "200", validated: true, confidence: 0.9 };
  assert.equal(b.editBorne(pt, "x", "150").validated, false);
  assert.equal(b.editBorne(pt, "label", "B2").validated, false);
  assert.equal(b.editBorne(pt, "y", "250").x, "100"); // autres champs inchangés
});

test("confirmer parcelle désactivé tant que toutes les bornes ne sont pas validées", () => {
  const valid = (validated) => ["B1", "B2", "B3"].map((l, i) => ({ label: l, x: `${i}`, y: `${i}`, validated }));
  assert.equal(b.canConfirmParcel(valid(false)), false);
  // une seule non validée → false
  const mixed = valid(true);
  mixed[1].validated = false;
  assert.equal(b.canConfirmParcel(mixed), false);
  // toutes validées → true
  assert.equal(b.canConfirmParcel(valid(true)), true);
  // moins de 3 bornes → false
  assert.equal(b.canConfirmParcel(valid(true).slice(0, 2)), false);
  // coordonnée invalide → false
  const badCoord = valid(true);
  badCoord[0].x = "";
  assert.equal(b.canConfirmParcel(badCoord), false);
});

test("borneToApi n'envoie jamais confidence=0 quand absente (null), garde 0 réel", () => {
  assert.deepEqual(b.borneToApi({ confidence: null }), { confidence: null, validated: false });
  assert.deepEqual(b.borneToApi({}), { confidence: null, validated: false });
  assert.deepEqual(b.borneToApi({ confidence: 0, validated: true }), { confidence: 0, validated: true });
});
