import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    ".nas-deploy/**",
    ".nas-maintenance/**",
    ".pnpm-store-local/**",
    ".pytest_cache/**",
    "agent/.pytest_cache/**",
    "agent/.pytest-*/**",
    "pytest-*/**",
    "tmp/pytest-*/**",
    "tmp/**",
    ".local-ui-check/**",
    "node_modules.corrupt-*/**",
    "dist/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
