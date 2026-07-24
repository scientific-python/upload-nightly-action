import js from '@eslint/js';
import globals from 'globals';
import prettier from 'eslint-config-prettier';

// The scripts under scripts/ and .github/scripts/ are loaded by
// actions/github-script, which injects `github`, `context`, and `core` as
// function parameters, so no extra globals are needed beyond Node's.
export default [
  {
    files: ['scripts/**/*.js', '.github/scripts/**/*.js'],
    ...js.configs.recommended,
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: 'commonjs',
      globals: { ...globals.node },
    },
  },
  prettier,
];
