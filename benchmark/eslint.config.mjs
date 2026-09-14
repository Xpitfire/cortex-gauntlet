// Flat ESLint config the Gauntlet scorer runs over generated JS/TS repos in an isolated tree
// (gauntlet/analysis/lint_types.py::_eslint_lint_issues). Style/quality rules only — `tsc` does the
// type-checking and undefined-name detection, so `no-undef` is off here (browser/node globals vary
// across generated apps and would otherwise be false positives). The deps below resolve from this
// directory's node_modules; run `npm install` here to activate eslint lint scoring.
import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default [
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    rules: {
      "no-undef": "off",
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": "warn",
      "@typescript-eslint/no-explicit-any": "off",
    },
  },
];
