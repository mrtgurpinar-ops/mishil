// @ts-nocheck
const fs = require('fs');
const path = require('path');
const ts = require('typescript');

function loadTs(relativePath) {
  const filePath = path.resolve(__dirname, '..', relativePath);
  const source = fs.readFileSync(filePath, 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const mod = { exports: {} };
  new Function('exports', 'require', 'module', '__filename', '__dirname', output)(
    mod.exports, require, mod, filePath, path.dirname(filePath),
  );
  return mod.exports;
}

describe('Expo Router +native-intent deep-link interceptor (v4.51.1)', () => {
  const nativeIntent = loadTs('app/+native-intent.tsx');

  test('isSleepDeepLink detects iOS Live Activity & Android notification URLs accurately', () => {
    expect(nativeIntent.isSleepDeepLink('misilbaby://sleep')).toBe(true);
    expect(nativeIntent.isSleepDeepLink('misilbaby:///sleep')).toBe(true);
    expect(nativeIntent.isSleepDeepLink('misilbaby://sleep?source=live_activity')).toBe(true);
    expect(nativeIntent.isSleepDeepLink('MISILBABY://SLEEP/')).toBe(true);
    expect(nativeIntent.isSleepDeepLink('/sleep')).toBe(true);
    expect(nativeIntent.isSleepDeepLink('sleep')).toBe(true);

    expect(nativeIntent.isSleepDeepLink('')).toBe(false);
    expect(nativeIntent.isSleepDeepLink(null)).toBe(false);
    expect(nativeIntent.isSleepDeepLink(undefined)).toBe(false);
    expect(nativeIntent.isSleepDeepLink('misilbaby://')).toBe(false);
    expect(nativeIntent.isSleepDeepLink('/')).toBe(false);
    expect(nativeIntent.isSleepDeepLink('https://mishil-production.up.railway.app/app')).toBe(false);
  });

  test('redirectSystemPath normalizes misilbaby://sleep and unknown deep-links to root "/" without Unmatched Route', () => {
    expect(nativeIntent.redirectSystemPath({ path: 'misilbaby://sleep', initial: true })).toBe('/');
    expect(nativeIntent.redirectSystemPath({ path: 'misilbaby://sleep', initial: false })).toBe('/');
    expect(nativeIntent.redirectSystemPath({ path: 'misilbaby:///sleep?from=widget', initial: true })).toBe('/');
    expect(nativeIntent.redirectSystemPath({ path: '/sleep', initial: false })).toBe('/');
    expect(nativeIntent.redirectSystemPath({ path: '/', initial: true })).toBe('/');
    expect(nativeIntent.redirectSystemPath({ path: '', initial: true })).toBe('/');
  });
});
