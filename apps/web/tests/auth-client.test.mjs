import assert from "node:assert/strict";
import { test } from "node:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";

const repoRoot = path.resolve(import.meta.dirname, "..");
const sourcePath = path.join(repoRoot, "app", "lib", "authClient.ts");
const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "topoaudit-auth-test-"));
const compiledPath = path.join(tempDir, "authClient.js");

execFileSync(
  path.join(repoRoot, "node_modules", ".bin", "tsc"),
  [sourcePath, "--target", "ES2020", "--module", "NodeNext", "--moduleResolution", "NodeNext", "--types", "node", "--skipLibCheck", "--outDir", tempDir],
  { cwd: repoRoot, stdio: "inherit" },
);

const auth = await import(compiledPath);

test("authHeaders ajoute le header Authorization quand un token est présent", () => {
  assert.deepEqual(auth.authHeaders("abc.def.ghi"), { Authorization: "Bearer abc.def.ghi" });
});

test("authHeaders est vide sans token (mode démo local)", () => {
  assert.deepEqual(auth.authHeaders(null), {});
  assert.deepEqual(auth.authHeaders(undefined), {});
  assert.deepEqual(auth.authHeaders(""), {});
});

test("withAuth fusionne en-têtes de base et Authorization", () => {
  const headers = auth.withAuth("tok", { "Content-Type": "application/json" });
  assert.equal(headers["Content-Type"], "application/json");
  assert.equal(headers.Authorization, "Bearer tok");
});

test("withAuth sans token n'ajoute pas Authorization", () => {
  const headers = auth.withAuth(null, { "Content-Type": "application/json" });
  assert.equal(headers["Content-Type"], "application/json");
  assert.ok(!("Authorization" in headers));
});
