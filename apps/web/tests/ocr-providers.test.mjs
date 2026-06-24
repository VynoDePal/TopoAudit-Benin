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

test("provider OCR par défaut = gemini (workflow inchangé)", () => {
  assert.equal(m.DEFAULT_OCR_PROVIDER, "gemini");
});
