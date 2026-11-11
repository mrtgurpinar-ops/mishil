// @ts-nocheck
const fs = require('fs');
const path = require('path');
const ts = require('typescript');

function createHarness(overrides = {}) {
  const storageMap = new Map(Object.entries(overrides.initialStorage || {}));
  let isAvailableImpl = overrides.isAvailableAsync || (async () => true);
  let requestReviewImpl = overrides.requestReview || (async () => {});
  const calls = {
    isAvailable: 0,
    requestReview: 0,
    setItem: 0,
  };

  const filePath = path.resolve(__dirname, '../features/review/storeReviewService.ts');
  const source = fs.readFileSync(filePath, 'utf8');
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      esModuleInterop: true,
    },
  });

  const mod = { exports: {} };
  const asyncStorageMock = {
    getItem: async (k) => (storageMap.has(k) ? storageMap.get(k) : null),
    setItem: async (k, v) => {
      calls.setItem += 1;
      storageMap.set(k, String(v));
    },
  };
  const customRequire = (id) => {
    if (id === '@react-native-async-storage/async-storage') {
      return { default: asyncStorageMock, __esModule: true, ...asyncStorageMock };
    }
    if (id === 'expo-store-review') {
      return {
        isAvailableAsync: async (...args) => {
          calls.isAvailable += 1;
          return isAvailableImpl(...args);
        },
        requestReview: async (...args) => {
          calls.requestReview += 1;
          return requestReviewImpl(...args);
        },
      };
    }
    return require(id);
  };

  const fn = new Function('exports', 'require', 'module', '__filename', '__dirname', transpiled.outputText);
  fn(mod.exports, customRequire, mod, filePath, path.dirname(filePath));

  return {
    service: mod.exports,
    storageMap,
    calls,
  };
}

describe('storeReviewService Unit Tests', () => {
  const BASE_NOW = 1794355200000; // 2026-11-11T00:00:00.000Z

  it('triggers native StoreReview.requestReview and persists 45-day timestamp when available', async () => {
    const { service, storageMap, calls } = createHarness();
    const res = await service.triggerNativeStoreReview({ nowMs: BASE_NOW });

    expect(res).toEqual({
      triggered: true,
      reason: 'ok',
      timestamp: BASE_NOW,
    });
    expect(calls.isAvailable).toBe(1);
    expect(calls.requestReview).toBe(1);
    expect(storageMap.get(service.NATIVE_REVIEW_STORAGE_KEY)).toBe(String(BASE_NOW));
  });

  it('enforces 45-day cooldown and allows triggering again once 45 days have elapsed', async () => {
    const { service, calls } = createHarness({
      initialStorage: {
        '@mishil_native_review_last_ts': String(BASE_NOW),
      },
    });

    // 10 gün sonra: bloklanmalı
    const blockedRes = await service.triggerNativeStoreReview({
      nowMs: BASE_NOW + 10 * 24 * 60 * 60 * 1000,
    });
    expect(blockedRes.triggered).toBe(false);
    expect(blockedRes.reason).toBe('cooldown');
    expect(calls.requestReview).toBe(0);

    // 45 gün + 1 saniye sonra: izin verilmeli
    const afterCooldownNow = BASE_NOW + service.NATIVE_REVIEW_COOLDOWN_MS + 1000;
    const allowedRes = await service.triggerNativeStoreReview({
      nowMs: afterCooldownNow,
    });
    expect(allowedRes).toEqual({
      triggered: true,
      reason: 'ok',
      timestamp: afterCooldownNow,
    });
    expect(calls.requestReview).toBe(1);
  });

  it('does NOT call requestReview or consume 45-day quota when native review is unavailable (e.g. TestFlight / old binary)', async () => {
    const { service, storageMap, calls } = createHarness({
      isAvailableAsync: async () => false,
    });

    const res = await service.triggerNativeStoreReview({ nowMs: BASE_NOW });
    expect(res).toEqual({
      triggered: false,
      reason: 'unavailable',
    });
    expect(calls.requestReview).toBe(0);
    expect(storageMap.has(service.NATIVE_REVIEW_STORAGE_KEY)).toBe(false);
  });

  it('deduplicates concurrent calls while a native review prompt is in flight', async () => {
    let resolvePrompt;
    const { service, calls } = createHarness({
      requestReview: () =>
        new Promise((resolve) => {
          resolvePrompt = resolve;
        }),
    });

    const p1 = service.triggerNativeStoreReview({ nowMs: BASE_NOW });
    const p2 = service.triggerNativeStoreReview({ nowMs: BASE_NOW + 50 });

    const secondResult = await p2;
    expect(secondResult).toEqual({
      triggered: false,
      reason: 'in_flight',
    });

    // Allow async getItem + isAvailableAsync microtasks to reach requestReview()
    while (typeof resolvePrompt !== 'function') {
      await Promise.resolve();
    }
    resolvePrompt();

    const firstResult = await p1;
    expect(firstResult.triggered).toBe(true);
    expect(calls.requestReview).toBe(1);
  });

  it('catches native errors gracefully without throwing or consuming cooldown quota', async () => {
    const { service, storageMap } = createHarness({
      requestReview: async () => {
        throw new Error('SKStoreReviewController presentation failed');
      },
    });

    const res = await service.triggerNativeStoreReview({ nowMs: BASE_NOW });
    expect(res).toEqual({
      triggered: false,
      reason: 'error',
    });
    expect(storageMap.has(service.NATIVE_REVIEW_STORAGE_KEY)).toBe(false);
  });
});
