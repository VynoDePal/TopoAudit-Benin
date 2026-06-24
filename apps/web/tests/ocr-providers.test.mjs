import assert from "node:assert/strict";
import { test } from "node:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";

const repoRoot = path.resolve(import.meta.dirname, "..");
const sourcePath = path.join(repoRoot, "app", "lib", "ocrProviders.ts");
const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "topoaudit-ocrprov-"));
const compiledPath = path.join(tempDir, "ocrProviders.js");

execFileSync(
  path.join(repoRoot, "node_modules", ".bin", "tsc"),
  [sourcePath, "--target", "ES2020", "--module", "NodeNext", "--moduleResolution", "NodeNext", "--skipLibCheck", "--outDir", tempDir],
  { cwd: repoRoot, stdio: "inherit" },
);

const m = await import(compiledPath);

test("le select propose Gemma/Gemini, Mistral OCR 4 et Mock OCR", () => {
  assert.deepEqual(m.OCR_PROVIDERS.map((p) => p.id), ["gemini", "mistral", "mock"]);
});

test("ocrProviderLabel affiche 'Mistral OCR 4' pour provider=mistral", () => {
  assert.equal(m.ocrProviderLabel("mistral", "fr"), "Mistral OCR 4");
  assert.equal(m.ocrProviderLabel("gemini", "fr"), "Gemma 4 / Gemini");
  assert.equal(m.ocrProviderLabel("mock", "fr"), "Mock OCR");
  // provider réel inconnu (ex. fallback azure) → id brut, pas de crash.
  assert.equal(m.ocrProviderLabel("azure", "fr"), "azure");
});

test("le provider choisi est envoyé dans l'URL OCR (?provider=)", () => {
  assert.equal(
    m.ocrRequestPath("proj1", "doc1", "mistral"),
    "/projects/proj1/documents/doc1/ocr?provider=mistral",
  );
  assert.ok(m.ocrRequestPath("p", "d", "gemini").includes("?provider=gemini"));
});

test("provider OCR par défaut = gemini (Gemma recommandé pour plans topo)", () => {
  assert.equal(m.DEFAULT_OCR_PROVIDER, "gemini");
});

test("pickDefaultProvider : premier configuré dans l'ordre gemini > mistral > mock", () => {
  // gemini configuré → gemini (Gemma d'abord, pas Mistral)
  assert.equal(
    m.pickDefaultProvider([
      { id: "gemini", configured: true },
      { id: "mistral", configured: true },
      { id: "mock", configured: true },
    ]),
    "gemini",
  );
  // gemini absent → mistral
  assert.equal(
    m.pickDefaultProvider([
      { id: "gemini", configured: false },
      { id: "mistral", configured: true },
      { id: "mock", configured: true },
    ]),
    "mistral",
  );
  // aucun des deux → mock
  assert.equal(
    m.pickDefaultProvider([
      { id: "gemini", configured: false },
      { id: "mistral", configured: false },
      { id: "mock", configured: true },
    ]),
    "mock",
  );
  // liste vide → mock (toujours un défaut)
  assert.equal(m.pickDefaultProvider([]), "mock");
});

test("ocrProviderStatusLabel : recommandé / rapide-expérimental / démo locale (+ clé absente)", () => {
  assert.equal(
    m.ocrProviderStatusLabel({ id: "gemini", configured: true, selectable: true }, "fr"),
    "Gemma 4 / Gemini — recommandé",
  );
  assert.equal(
    m.ocrProviderStatusLabel({ id: "mistral", configured: true, selectable: true }, "fr"),
    "Mistral OCR 4 — rapide / expérimental",
  );
  assert.equal(m.ocrProviderStatusLabel({ id: "mock", configured: true, selectable: true }, "fr"), "Mock OCR — démo locale");
  // non configuré : nature conservée + statut de clé
  assert.equal(
    m.ocrProviderStatusLabel({ id: "gemini", configured: false, selectable: true }, "fr"),
    "Gemma 4 / Gemini — recommandé · clé absente (fallback mock)",
  );
  assert.equal(
    m.ocrProviderStatusLabel({ id: "mistral", configured: false, selectable: false }, "fr"),
    "Mistral OCR 4 — rapide / expérimental · clé absente",
  );
});

test("parcelsAfterOcr : aucune borne → écran vidé (jamais de données de démo)", () => {
  const empty = m.parcelsAfterOcr([]);
  assert.deepEqual(empty.parcels, []);
  assert.equal(empty.activeIdx, 0);
  assert.equal(empty.emptyExtraction, true);
  // bornes extraites → on les garde
  const filled = m.parcelsAfterOcr([{ id: "p1" }, { id: "p2" }]);
  assert.equal(filled.parcels.length, 2);
  assert.equal(filled.emptyExtraction, false);
});
