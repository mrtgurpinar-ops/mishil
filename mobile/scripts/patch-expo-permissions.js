const fs = require('fs');
const path = require('path');

const targetFile = path.join(
  __dirname,
  '..',
  'node_modules',
  'expo-modules-core',
  'android',
  'src',
  'main',
  'java',
  'expo',
  'modules',
  'adapters',
  'react',
  'permissions',
  'PermissionsService.kt'
);

if (fs.existsSync(targetFile)) {
  let content = fs.readFileSync(targetFile, 'utf8');
  const target = 'return requestedPermissions.contains(permission)';
  const replacement = 'return requestedPermissions?.contains(permission) == true';

  if (content.includes(target)) {
    content = content.replace(target, replacement);
    fs.writeFileSync(targetFile, content, 'utf8');
    console.log('[patch-expo-permissions] Successfully patched PermissionsService.kt for Android SDK 36 compatibility.');
  } else if (content.includes(replacement)) {
    console.log('[patch-expo-permissions] PermissionsService.kt is already patched.');
  } else {
    console.warn('[patch-expo-permissions] Target string not found in PermissionsService.kt');
  }
} else {
  console.log('[patch-expo-permissions] PermissionsService.kt not found, skipping patch.');
}
