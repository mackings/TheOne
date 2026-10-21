import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const outer = (...layers) => layers.map((l) => ({ group: [`@/${l}/*`, `@/${l}`], message: `This layer must not depend on ${l}.` }));

// The dependency rule: domain <- application <- presentation, with infrastructure plugged in at the composition root.
const layers = [
  {
    files: ["src/domain/**"],
    rules: { "no-restricted-imports": ["error", { paths: ["react", "next"], patterns: outer("application", "infrastructure", "presentation", "app") }] },
  },
  {
    files: ["src/application/**"],
    rules: { "no-restricted-imports": ["error", { paths: ["react", "next"], patterns: outer("infrastructure", "presentation", "app") }] },
  },
  {
    files: ["src/presentation/**"],
    rules: {
      "no-restricted-imports": ["error", {
        patterns: [{ group: ["@/infrastructure/http", "@/infrastructure/http/*"], message: "Use the gateways from @/presentation/hooks/gateways." }, ...outer("app")],
      }],
    },
  },
];

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  ...layers,
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts", "public/mediapipe/**"]),
]);

export default eslintConfig;
