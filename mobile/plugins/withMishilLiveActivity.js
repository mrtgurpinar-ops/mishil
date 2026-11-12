const { withInfoPlist, withXcodeProject, withDangerousMod, IOSConfig } = require('@expo/config-plugins');
const fs = require('fs');
const path = require('path');

const WIDGET_TARGET_NAME = 'MishilLiveActivity';
const WIDGET_BUNDLE_ID_SUFFIX = 'LiveSleepWidget';
const WIDGET_DEPLOYMENT_TARGET = '16.2';
const SOURCE_DIR_NAME = 'targets/MishilLiveActivity';

/**
 * Expo Config Plugin: withMishilLiveActivity
 *
 * 1. Ana uygulama Info.plist'ine NSSupportsLiveActivities ekler.
 * 2. targets/MishilLiveActivity/ içindeki Swift + Info.plist dosyalarını ios/MishilLiveActivity/'e kopyalar.
 * 3. ios/MishilLiveActivity native app-extension hedefini (idempotent) xcodeproj'a ekler.
 */
function withLiveActivityInfoPlist(config) {
  return withInfoPlist(config, (cfg) => {
    cfg.modResults.NSSupportsLiveActivities = true;
    cfg.modResults.NSSupportsLiveActivitiesFrequentUpdates = false;
    return cfg;
  });
}

function withLiveActivitySourceCopy(config) {
  return withDangerousMod(config, [
    'ios',
    async (cfg) => {
      const projectRoot = cfg.modRequest.projectRoot;
      const platformRoot = cfg.modRequest.platformProjectRoot;
      const sourceDir = path.join(projectRoot, SOURCE_DIR_NAME);
      const destDir = path.join(platformRoot, WIDGET_TARGET_NAME);

      if (!fs.existsSync(sourceDir)) {
        return cfg;
      }
      if (!fs.existsSync(destDir)) {
        fs.mkdirSync(destDir, { recursive: true });
      }

      const files = fs.readdirSync(sourceDir);
      for (const file of files) {
        const src = path.join(sourceDir, file);
        const dest = path.join(destDir, file);
        if (fs.statSync(src).isFile()) {
          fs.copyFileSync(src, dest);
        }
      }

      return cfg;
    },
  ]);
}

function targetAlreadyExists(project, targetName) {
  const targets = project.pbxNativeTargetSection();
  return Object.keys(targets).some((key) => {
    const t = targets[key];
    return t && (t.name === targetName || t.name === `"${targetName}"`);
  });
}

function withLiveActivityXcodeTarget(config) {
  return withXcodeProject(config, (cfg) => {
    const project = cfg.modResults;

    if (targetAlreadyExists(project, WIDGET_TARGET_NAME)) {
      return cfg;
    }

    // Fresh Expo prebuild pbxproj dosyalarında bu bölümler boş gelebilir; addTargetDependency çökmesin
    project.hash.project.objects['PBXTargetDependency'] =
      project.hash.project.objects['PBXTargetDependency'] || {};
    project.hash.project.objects['PBXContainerItemProxy'] =
      project.hash.project.objects['PBXContainerItemProxy'] || {};

    const mainBundleId = (config.ios && config.ios.bundleIdentifier) || 'com.levitas.misilbaby';
    const widgetBundleId = `${mainBundleId}.${WIDGET_BUNDLE_ID_SUFFIX}`;
    const marketingVersion = config.version || '1.0.0';
    const buildNumber = (config.ios && config.ios.buildNumber) || '1';

    const pbxGroup = project.addPbxGroup(
      [
        'MishilLiveActivityBundle.swift',
        'MishilLiveActivityLiveActivity.swift',
        'MishilSleepAttributes.swift',
        'Info.plist',
      ],
      WIDGET_TARGET_NAME,
      WIDGET_TARGET_NAME
    );

    const firstProj = project.getFirstProject();
    const mainGroupUuid = firstProj && firstProj.firstProject && firstProj.firstProject.mainGroup;
    if (mainGroupUuid && pbxGroup && pbxGroup.uuid) {
      project.addToPbxGroup(pbxGroup.uuid, mainGroupUuid);
    }

    // addTarget(..., 'app_extension', ...) otomatik olarak CopyFiles (Embed) fazını ve
    // ana hedefe PBXTargetDependency bağlantısını oluşturur.
    const target = project.addTarget(
      WIDGET_TARGET_NAME,
      'app_extension',
      WIDGET_TARGET_NAME,
      widgetBundleId
    );

    project.addBuildPhase(
      [
        `${WIDGET_TARGET_NAME}/MishilLiveActivityBundle.swift`,
        `${WIDGET_TARGET_NAME}/MishilLiveActivityLiveActivity.swift`,
        `${WIDGET_TARGET_NAME}/MishilSleepAttributes.swift`,
      ],
      'PBXSourcesBuildPhase',
      'Sources',
      target.uuid
    );
    project.addBuildPhase([], 'PBXResourcesBuildPhase', 'Resources', target.uuid);
    project.addBuildPhase([], 'PBXFrameworksBuildPhase', 'Frameworks', target.uuid);

    const configurations = project.pbxXCBuildConfigurationSection();
    Object.keys(configurations).forEach((key) => {
      const entry = configurations[key];
      if (!entry || typeof entry !== 'object' || !entry.buildSettings) return;
      const prodName = entry.buildSettings.PRODUCT_NAME;
      if (prodName !== `"${WIDGET_TARGET_NAME}"` && prodName !== WIDGET_TARGET_NAME) return;
      entry.buildSettings.PRODUCT_BUNDLE_IDENTIFIER = `"${widgetBundleId}"`;
      entry.buildSettings.IPHONEOS_DEPLOYMENT_TARGET = WIDGET_DEPLOYMENT_TARGET;
      entry.buildSettings.SWIFT_VERSION = '5.0';
      entry.buildSettings.TARGETED_DEVICE_FAMILY = '"1"';
      entry.buildSettings.SKIP_INSTALL = 'YES';
      entry.buildSettings.GENERATE_INFOPLIST_FILE = 'NO';
      entry.buildSettings.INFOPLIST_FILE = `"${WIDGET_TARGET_NAME}/Info.plist"`;
      entry.buildSettings.CURRENT_PROJECT_VERSION = `"${buildNumber}"`;
      entry.buildSettings.MARKETING_VERSION = `"${marketingVersion}"`;
      entry.buildSettings.CODE_SIGN_STYLE = 'Automatic';
      if (config.ios && config.ios.appleTeamId) {
        entry.buildSettings.DEVELOPMENT_TEAM = config.ios.appleTeamId;
      }
      entry.buildSettings.LD_RUNPATH_SEARCH_PATHS =
        '"$(inherited) @executable_path/Frameworks @executable_path/../../Frameworks"';
    });

    return cfg;
  });
}

const withMishilLiveActivity = (config) => {
  config = withLiveActivityInfoPlist(config);
  config = withLiveActivitySourceCopy(config);
  config = withLiveActivityXcodeTarget(config);
  return config;
};

module.exports = withMishilLiveActivity;
