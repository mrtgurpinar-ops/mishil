const { withDangerousMod } = require('@expo/config-plugins');
const fs = require('fs');
const path = require('path');

/**
 * Expo Config Plugin: withMinDeploymentTarget
 * 
 * Enforces a minimum IPHONEOS_DEPLOYMENT_TARGET across all CocoaPods targets
 * (including third-party resource bundles like AsyncStorage, RNSVG, RevenueCat)
 * to comply with Xcode 16+ strict iOS 15.0+ requirement.
 */
const withMinDeploymentTarget = (config) => {
  return withDangerousMod(config, [
    'ios',
    async (cfg) => {
      const podfilePath = path.join(cfg.modRequest.platformProjectRoot, 'Podfile');
      if (!fs.existsSync(podfilePath)) {
        return cfg;
      }

      let podfileContent = fs.readFileSync(podfilePath, 'utf8');

      const postInstallSnippet = `
    # --- [withMinDeploymentTarget] Enforce iOS 15.1 on all Pod targets & resource bundles ---
    installer.pods_project.targets.each do |target|
      target.build_configurations.each do |config|
        current_target = config.build_settings['IPHONEOS_DEPLOYMENT_TARGET']
        if current_target.nil? || current_target.to_f < 15.1
          config.build_settings['IPHONEOS_DEPLOYMENT_TARGET'] = '15.1'
        end
      end
    end
`;

      if (!podfileContent.includes('[withMinDeploymentTarget]')) {
        if (podfileContent.includes('post_install do |installer|')) {
          podfileContent = podfileContent.replace(
            'post_install do |installer|',
            `post_install do |installer|${postInstallSnippet}`
          );
        } else {
          podfileContent += `\npost_install do |installer|${postInstallSnippet}\nend\n`;
        }

        fs.writeFileSync(podfilePath, podfileContent, 'utf8');
      }

      return cfg;
    },
  ]);
};

module.exports = withMinDeploymentTarget;
