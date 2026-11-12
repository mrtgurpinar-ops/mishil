require 'json'

package = JSON.parse(File.read(File.join(__dir__, '..', 'package.json')))

Pod::Spec.new do |s|
  s.name           = 'MishilLockScreen'
  s.version        = package['version']
  s.summary        = 'Mışıl Baby native lock screen audio + Live Activity sleep tracker'
  s.description     = 'Native AVAudioSession/MPNowPlayingInfoCenter lullaby playback and ActivityKit live sleep tracking for Mışıl Baby.'
  s.license        = 'Proprietary'
  s.author         = 'Levitas'
  s.homepage       = 'https://mishil-production.up.railway.app'
  s.platforms      = { :ios => '15.1' }
  s.swift_version  = '5.0'
  s.source         = { :git => '' }
  s.static_framework = true

  s.dependency 'ExpoModulesCore'

  s.source_files = '**/*.{h,m,swift}'
end
