import assert from "node:assert/strict";
import { test } from "node:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";

const repoRoot = path.resolve(import.meta.dirname, "..");
const sourcePath = path.join(repoRoot, "app", "lib", "crsClient.ts");
const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "topoaudit-crs-"));
const compiledPath = path.join(tempDir, "crsClient.js");

execFileSync(
  path.join(repoRoot, "node_modules", ".bin", "tsc"),
  [sourcePath, "--target", "ES2020", "--module", "NodeNext", "--moduleResolution", "NodeNext", "--types", "node", "--skipLibCheck", "--esModuleInterop", "--outDir", tempDir],
  { cwd: repoRoot, stdio: "inherit" },
);

// proj4 (CJS) doit être résolvable depuis le dossier temporaire.
fs.symlinkSync(path.join(repoRoot, "node_modules"), path.join(tempDir, "node_modules"), "dir");
const crs = await import(compiledPath);

test("EPSG transformables, statuts non géoréférencés non transformables", () => {
  for (const ok of ["EPSG:32631", "EPSG_32631", "EPSG:4326", "EPSG_4326"]) {
    assert.equal(crs.isTransformableCrs(ok), true, ok);
  }
  for (const bad of ["LOCAL_ONLY", "UNKNOWN_CRS", "NEEDS_GEOREFERENCING", "local", "", null, undefined]) {
    assert.equal(crs.isTransformableCrs(bad), false, String(bad));
  }
});

test("toWgs84 LÈVE pour les CRS non transformables (jamais de projection implicite)", () => {
  for (const bad of ["LOCAL_ONLY", "UNKNOWN_CRS", "NEEDS_GEOREFERENCING", "local"]) {
    assert.throws(() => crs.toWgs84(403825, 707630, bad), /non transformable/, bad);
  }
});

test("toWgs84 : EPSG:4326 passe-plat, EPSG:32631 projette en lon/lat Bénin", () => {
  assert.deepEqual(crs.toWgs84(2.35, 9.31, "EPSG:4326"), [2.35, 9.31]);
  const [lon, lat] = crs.toWgs84(403825.84, 707630.38, "EPSG:32631");
  assert.ok(lon > 0.5 && lon < 4.5, `lon=${lon}`);
  assert.ok(lat > 6 && lat < 13.5, `lat=${lat}`);
});

test("carte Esri affichée uniquement pour un CRS transformable", () => {
  // La carte Esri (MapLibre) ne s'affiche que si le CRS est transformable.
  for (const noEsri of ["LOCAL_ONLY", "UNKNOWN_CRS", "NEEDS_GEOREFERENCING", "local"]) {
    assert.equal(crs.isTransformableCrs(noEsri), false, `${noEsri} ne doit PAS afficher Esri`);
  }
  for (const esri of ["EPSG:32631", "EPSG:4326"]) {
    assert.equal(crs.isTransformableCrs(esri), true, `${esri} peut afficher Esri`);
  }
});
