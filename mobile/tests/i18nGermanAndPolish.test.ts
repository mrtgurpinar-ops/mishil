// @ts-nocheck
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const ts = require('typescript');

const APP_HTML_PATH = path.resolve(__dirname, '../../public/app.html');

function extractFuncBlock(code, signature) {
  const start = code.indexOf(signature);
  if (start === -1) throw new Error(`Missing signature: ${signature}`);
  let depth = 0;
  let started = false;
  for (let i = start; i < code.length; i++) {
    const ch = code[i];
    if (ch === '{') {
      depth++;
      started = true;
    } else if (ch === '}') {
      depth--;
      if (started && depth === 0) {
        return code.slice(start, i + 1);
      }
    }
  }
  throw new Error(`Unclosed block for: ${signature}`);
}

function loadCareNotificationEngine() {
  const filePath = path.resolve(__dirname, '../features/notifications/careNotificationEngine.ts');
  const source = fs.readFileSync(filePath, 'utf8');
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
  });
  const mod = { exports: {} };
  const customRequire = (id) => {
    if (id === 'expo-notifications') return {};
    if (id === 'react-native') return { Platform: { OS: 'ios' } };
    if (id === '@react-native-async-storage/async-storage') return { getItem: async () => null, setItem: async () => {} };
    return require(id);
  };
  const fn = new Function('exports', 'require', 'module', '__filename', '__dirname', transpiled.outputText);
  fn(mod.exports, customRequire, mod, filePath, path.dirname(filePath));
  return mod.exports;
}

describe('Mışıl Baby v4.50.0 — German (DE / DACH) & Multilingual Polish Suite', () => {
  const html = fs.readFileSync(APP_HTML_PATH, 'utf8');
  const scriptCode = html.slice(html.indexOf('<script>') + 8, html.lastIndexOf('</script>'));

  it('1. normalizeLang & resolveInitialLanguage support de-DE/de-CH/de-AT and Build 67 backward-compatible upgrade', () => {
    const snippet = [
      extractFuncBlock(scriptCode, 'function normalizeLang('),
      extractFuncBlock(scriptCode, 'function isSupportedLangCode('),
      extractFuncBlock(scriptCode, 'function resolveInitialLanguage('),
    ].join('\n');

    function runLangInit({ savedLang = null, explicit = null, navLang = 'en-US', query = '' }) {
      const store = {};
      if (savedLang !== null) store.mishil_lang = savedLang;
      if (explicit !== null) store.mishil_lang_explicit = explicit;
      const ctx = {
        window: { location: { search: query } },
        URLSearchParams,
        navigator: { language: navLang, languages: [navLang] },
        Intl,
        localStorage: {
          getItem: (k) => (k in store ? store[k] : null),
          setItem: (k, v) => { store[k] = String(v); },
        },
      };
      vm.runInNewContext(snippet, ctx);
      return {
        resolved: ctx.resolveInitialLanguage(),
        normDe: ctx.normalizeLang('de-DE'),
        normCh: ctx.normalizeLang('de-CH'),
        normAt: ctx.normalizeLang('de-AT'),
        normFr: ctx.normalizeLang('fr-FR'),
        store,
      };
    }

    // Fresh German / Swiss / Austrian devices resolve to 'de'
    expect(runLangInit({ navLang: 'de-DE' }).resolved).toBe('de');
    expect(runLangInit({ navLang: 'de-CH' }).resolved).toBe('de');
    expect(runLangInit({ navLang: 'de-AT' }).resolved).toBe('de');
    expect(runLangInit({ navLang: 'fr-FR' }).normFr).toBe('en');

    // Build 66 -> Build 67 upgrade: auto-saved 'en' without explicit flag upgrades to 'de' on German device
    const upgraded = runLangInit({ savedLang: 'en', explicit: null, navLang: 'de-DE' });
    expect(upgraded.resolved).toBe('de');

    // User explicitly picked 'en' on a German device -> stays 'en'
    const explicitEn = runLangInit({ savedLang: 'en', explicit: '1', navLang: 'de-DE' });
    expect(explicitEn.resolved).toBe('en');

    // Invalid query param (?lang=fr) does NOT lock mishil_lang_explicit=1 and still upgrades de-DE
    const invalidQueryOnDe = runLangInit({ savedLang: 'en', explicit: null, navLang: 'de-DE', query: '?lang=fr' });
    expect(invalidQueryOnDe.resolved).toBe('de');
    expect(invalidQueryOnDe.store.mishil_lang_explicit).toBeUndefined();
  });

  it('2. resolveLocalizedRoutineCopy eliminates mixed-language routines across TR <-> EN <-> DE', () => {
    const snippet = [
      extractFuncBlock(scriptCode, 'function normalizeLang('),
      'let __activeLang = "tr"; function getAppLang() { return __activeLang; }',
      extractFuncBlock(scriptCode, 'function _planNormLang('),
      extractFuncBlock(scriptCode, 'function _planActiveLang('),
      extractFuncBlock(scriptCode, 'function resolveLocalizedRoutineCopy('),
      extractFuncBlock(scriptCode, 'function formatRoutineTitleDisplay('),
      extractFuncBlock(scriptCode, 'function formatRoutineDetailDisplay('),
    ].join('\n');
    const ctx = {};
    vm.runInNewContext(snippet, ctx);

    // Entry originally logged in Turkish
    const trFeed = {
      id: 'rt_1',
      type: 'feeding',
      title: 'Beslenme',
      detail: 'Anne Sütü • 20 dk • sağ göğüs',
      method: 'breast',
      durationMin: 20,
      note: 'sağ göğüs',
    };

    const enCopy = ctx.resolveLocalizedRoutineCopy(trFeed, 'en');
    expect(enCopy.title).toBe('Milk / Feeding');
    expect(enCopy.detail).toContain('Breast Milk');
    expect(enCopy.detail).toContain('20 min');

    const deCopy = ctx.resolveLocalizedRoutineCopy(trFeed, 'de');
    expect(deCopy.title).toBe('Mahlzeit');
    expect(deCopy.detail).toContain('Muttermilch');
    expect(deCopy.detail).toContain('20 Min.');

    const backToTr = ctx.resolveLocalizedRoutineCopy(trFeed, 'tr');
    expect(backToTr.title).toBe('Beslenme');
    expect(backToTr.detail).toContain('Anne Sütü');

    // Diaper & Sleep cross-language normalization
    const trDiaper = { id: 'rt_2', type: 'diaper', title: 'Bez Değişimi', detail: 'Islak (çiş)', kind: 'wet' };
    expect(ctx.resolveLocalizedRoutineCopy(trDiaper, 'de').title).toBe('Windelwechsel');
    expect(ctx.resolveLocalizedRoutineCopy(trDiaper, 'de').detail).toContain('Nass');
    expect(ctx.resolveLocalizedRoutineCopy(trDiaper, 'en').detail).toContain('Wet');

    const trSleep = { id: 'slp_1', type: 'sleep', sleepKind: 'nap', napIndex: 2, durationMins: 65, start: '13:00', end: '14:05', title: '2. Gündüz Uykusu (Nap 2)', detail: '65 dk Derin Uyku (13:00 - 14:05)' };
    expect(ctx.resolveLocalizedRoutineCopy(trSleep, 'de').title).toContain('2. Tagschlaf');
    expect(ctx.resolveLocalizedRoutineCopy(trSleep, 'en').title).toContain('Daytime Nap #2');

    // Legacy typeless German record ('Windelwechsel' / 'Nass (Urin)') translates cleanly to EN/TR
    const legacyDeDiaper = { id: 'rt_legacy_de', title: 'Windelwechsel', detail: 'Nass (Urin)' };
    expect(ctx.resolveLocalizedRoutineCopy(legacyDeDiaper, 'en').title).toBe('Diaper Change');
    expect(ctx.resolveLocalizedRoutineCopy(legacyDeDiaper, 'en').detail).toContain('Wet');
    expect(ctx.resolveLocalizedRoutineCopy(legacyDeDiaper, 'tr').title).toBe('Bez Değişimi');
  });

  it('3. Cultural date/clock ergonomics: EN uses Month|Day|Year CSS & 12h AM/PM labels; DE & TR keep Day|Month|Year & 24h', () => {
    expect(html).toContain('html[lang="en"] #quiz-step-1 .onb-combo-grid-3 > .onb-select-wrap:nth-child(2) { order: 1; }');
    expect(html).toContain('html[lang="en"] #quiz-step-1 .onb-combo-grid-3 > .onb-select-wrap:nth-child(1) { order: 2; }');

    const snippet = [
      'let __lang = "tr"; function getAppLang() { return __lang; }',
      extractFuncBlock(scriptCode, 'function _planNormLang('),
      extractFuncBlock(scriptCode, 'function _planActiveLang('),
      extractFuncBlock(scriptCode, 'function formatHourSelectOptionLabel('),
    ].join('\n');
    const ctx = { setLang: null };
    vm.runInNewContext(snippet + '\nsetLang = (l) => { __lang = l; };', ctx);

    ctx.setLang('en');
    expect(ctx.formatHourSelectOptionLabel(0)).toBe('00 (12 AM)');
    expect(ctx.formatHourSelectOptionLabel(14)).toBe('14 (2 PM)');

    ctx.setLang('de');
    expect(ctx.formatHourSelectOptionLabel(14)).toBe('14');
    ctx.setLang('tr');
    expect(ctx.formatHourSelectOptionLabel(14)).toBe('14');
  });

  it('4. prevQuizStep re-applies static DOM translations, CHANGELOG v4.50.0 has EN/DE, and EN/DE maps have 100% parity', () => {
    const prevBlock = extractFuncBlock(scriptCode, 'function prevQuizStep(');
    expect(prevBlock).toContain('applyStaticDomTranslations(getAppLang())');

    const enMatch = scriptCode.match(/const TR_TO_EN_EXACT_MAP = (\{[\s\S]*?\n  \});/);
    const deMatch = scriptCode.match(/const TR_TO_DE_EXACT_MAP = (\{[\s\S]*?\n  \});/);
    expect(enMatch).not.toBeNull();
    expect(deMatch).not.toBeNull();
    const enMap = vm.runInNewContext('(' + enMatch[1] + ')');
    const deMap = vm.runInNewContext('(' + deMatch[1] + ')');
    expect(Object.keys(deMap).length).toBe(Object.keys(enMap).length);
    expect(deMap['İşaretlenen: 0 / 0']).toBe('Erledigt: 0 / 0');

    expect(scriptCode).toContain("{ v: '4.50.0'");
    expect(scriptCode).toContain('itemsDe:');
  });

  it('5. CareNotificationEngine generates natural German (STIKO / BAG) vaccine, leap & sleep notifications', () => {
    const { buildCareNotificationPlan, DEFAULT_NOTIFICATION_SETTINGS, getVaccineMilestonesForCountry } = loadCareNotificationEngine();
    const refDate = new Date('2026-10-23T12:00:00.000Z');

    // German STIKO (DE) & Swiss BAG (CH) milestones have German labels
    const deMilestones = getVaccineMilestonesForCountry('DE');
    expect(deMilestones[0].labelDe).toContain('6-fach');
    const chMilestones = getVaccineMilestonesForCountry('CH');
    expect(chMilestones[0].labelDe).toContain('Pneumokokken');

    // Routine + Leap in German
    const bdate = new Date(refDate);
    bdate.setDate(bdate.getDate() - 131); // 2 days before week 19 leap
    const planDe = buildCareNotificationPlan(
      { babyName: 'Emilia', babyBdate: bdate.toISOString().split('T')[0] },
      { ...DEFAULT_NOTIFICATION_SETTINGS, lang: 'de', vaccineCountry: 'DE' },
      refDate,
      14
    );

    expect(planDe.length).toBeGreaterThan(0);
    const leapDe = planDe.find((x) => x.type === 'LEAP');
    expect(leapDe).toBeDefined();
    expect(leapDe.title).toContain('Entwicklungssprung');
    const routineDe = planDe.find((x) => x.type === 'ROUTINE_SLEEP');
    expect(routineDe).toBeDefined();
    expect(routineDe.title).toContain('Schläft Emilia');
    expect(routineDe.body).toContain('Einschlafen');

    // Cross-layer placeholder sync: DE placeholder ('Ihr Baby' / 'Dein Baby') translates cleanly when switched to EN/TR
    const switchedToEn = buildCareNotificationPlan(
      { babyName: 'Ihr Baby', babyBdate: bdate.toISOString().split('T')[0] },
      { ...DEFAULT_NOTIFICATION_SETTINGS, lang: 'en', vaccineCountry: 'DE' },
      refDate,
      14
    );
    const switchedRoutineEn = switchedToEn.find((x) => x.type === 'ROUTINE_SLEEP');
    expect(switchedRoutineEn.title).toContain('Your Baby');
    expect(switchedRoutineEn.title).not.toContain('Ihr Baby');

    // Malformed routineTime ('25:90') safely falls back to 20:30 instead of rolling to next day / NaN
    const malformedPlan = buildCareNotificationPlan(
      { babyName: 'Emilia', babyBdate: bdate.toISOString().split('T')[0] },
      { ...DEFAULT_NOTIFICATION_SETTINGS, lang: 'de', routineTime: '25:90' },
      refDate,
      3
    );
    const fallbackRoutine = malformedPlan.find((x) => x.type === 'ROUTINE_SLEEP');
    expect(fallbackRoutine).toBeDefined();
    expect(fallbackRoutine.date.getHours()).toBe(20);
    expect(fallbackRoutine.date.getMinutes()).toBe(30);
  });
});
