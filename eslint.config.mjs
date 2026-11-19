import globals from "globals";
import js from "@eslint/js";

export default [
  {
    files: ["assets/**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",           // app.js è uno script classico (funzioni globali per gli onclick)
      globals: { ...globals.browser },
    },
    rules: {
      ...js.configs.recommended.rules,
      "no-unused-vars": ["error", { args: "none", caughtErrors: "none" }],
      "no-restricted-globals": ["error",
        { name: "alert", message: "Usa ui.toast()" },
        { name: "confirm", message: "Usa ui.confirm()" },
        { name: "prompt", message: "Usa una finestra dell'app" }],
      "no-restricted-properties": ["error",
        { object: "window", property: "alert", message: "Usa ui.toast()" },
        { object: "window", property: "confirm", message: "Usa ui.confirm()" }],
      "eqeqeq": ["error", "smart"],
    },
  },
  {
    files: ["tools/**/*.mjs"],
    languageOptions: { ecmaVersion: 2023, sourceType: "module", globals: { ...globals.node } },
    rules: { ...js.configs.recommended.rules },
  },
];
