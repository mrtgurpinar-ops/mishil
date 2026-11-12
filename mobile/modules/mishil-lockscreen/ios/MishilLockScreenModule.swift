import ExpoModulesCore
import AVFoundation
import MediaPlayer
import UIKit

#if canImport(ActivityKit)
import ActivityKit
#endif

struct PlayAudioOptions: Record {
  @Field var id: String = ""
  @Field var url: String = ""
  @Field var title: String = ""
  @Field var subtitle: String? = nil
  @Field var volume: Double? = nil
  @Field var isVip: Bool = false
  @Field var previewBudgetMs: Double? = nil
}

struct StartLiveSleepOptions: Record {
  @Field var startEpochMs: Double = 0
  @Field var sleepLabel: String = ""
  @Field var subtitle: String? = nil
  @Field var babyName: String? = nil
  @Field var showBabyNameOnLockScreen: Bool? = nil
  @Field var lang: String? = nil
}

struct UpdateLiveSleepOptions: Record {
  @Field var startEpochMs: Double = 0
  @Field var sleepLabel: String? = nil
  @Field var subtitle: String? = nil
  @Field var babyName: String? = nil
  @Field var showBabyNameOnLockScreen: Bool? = nil
}

public class MishilLockScreenModule: Module {
  private var player: AVQueuePlayer?
  private var playerLooper: AVPlayerLooper?
  private var statusObservation: NSKeyValueObservation?

  private var currentId: String?
  private var currentTitle: String = ""
  private var currentSubtitle: String = "Mışıl Baby"
  private var isVipSession: Bool = true
  private var isPaused: Bool = false

  // Freemium 60sn izleme kotası — ProcessInfo.systemUptime monotonik, duvar saati manipülasyonuna karşı güvenli
  private static let freePreviewCapMs: Double = 60000
  private var cumulativePreviewUsedMs: Double = 0
  private var previewBudgetMs: Double = 0
  private var previewRemainingMs: Double = 0
  private var previewLastResumeUptime: Double = 0
  private var previewTimer: DispatchSourceTimer?

  // Canlı Uyku (ActivityKit) durumu — iOS 8 saatlik sistem sınırına karşı 7. saatte ön planda tazeleme destekli
  private static let activityStaleAfterSeconds: TimeInterval = 8 * 3600
  private static let activityMaxSleepSeconds: TimeInterval = 16 * 3600
  private static let activityRolloverThresholdMs: Double = 7 * 3600 * 1000
  private var sleepStartEpochMs: Double?
  private var activityCreatedAtEpochMs: Double?
  private var sleepLabelStore: String = ""
  private var sleepSubtitleStore: String = ""
  private var sleepBabyName: String?
  private var sleepShowBabyName: Bool = false

  public func definition() -> ModuleDefinition {
    Name("MishilLockScreen")

    Events("onPlaybackStateChanged")

    OnCreate {
      DispatchQueue.main.async {
        self.setupRemoteCommands()
      }
    }

    AsyncFunction("playAudio") { (options: PlayAudioOptions) -> Bool in
      return self.handlePlayAudio(options)
    }.runOnQueue(.main)

    AsyncFunction("pauseAudio") { () -> Void in
      self.pausePlayback(reason: "user")
    }.runOnQueue(.main)

    AsyncFunction("stopAudio") { () -> Void in
      self.stopPlayback(reason: "user")
    }.runOnQueue(.main)

    AsyncFunction("setAudioVolume") { (volume: Double) -> Void in
      self.player?.volume = Float(max(0, min(1, volume)))
    }.runOnQueue(.main)

    AsyncFunction("startLiveSleep") { (options: StartLiveSleepOptions) -> Bool in
      return self.handleStartLiveSleep(options)
    }.runOnQueue(.main)

    AsyncFunction("updateLiveSleep") { (options: UpdateLiveSleepOptions) -> Bool in
      return self.handleUpdateLiveSleep(options)
    }.runOnQueue(.main)

    AsyncFunction("stopLiveSleep") { () -> Void in
      self.handleStopLiveSleep()
    }.runOnQueue(.main)

    AsyncFunction("getLockScreenState") { () -> [String: Any?] in
      return self.currentStateDict()
    }.runOnQueue(.main)

    OnDestroy {
      self.previewTimer?.cancel()
      self.previewTimer = nil
    }
  }

  // MARK: - Audio playback

  private func ensureAudioSession() {
    let session = AVAudioSession.sharedInstance()
    try? session.setCategory(.playback, mode: .default, options: [])
    try? session.setActive(true)
  }

  private func handlePlayAudio(_ options: PlayAudioOptions) -> Bool {
    guard let url = URL(string: options.url) else { return false }
    // Önceki ücretsiz önizleme parçasından harcanan süreyi cumulativePreviewUsedMs içine işle
    if player != nil && !isVipSession {
      stopPlayback(reason: "track_switch")
    }
    ensureAudioSession()

    previewTimer?.cancel()
    previewTimer = nil

    let item = AVPlayerItem(url: url)
    let queuePlayer = AVQueuePlayer()
    queuePlayer.volume = Float(max(0, min(1, options.volume ?? 1.0)))
    let looper = AVPlayerLooper(player: queuePlayer, templateItem: item)

    statusObservation?.invalidate()
    statusObservation = item.observe(\.status, options: [.new]) { [weak self] observedItem, _ in
      guard let self = self else { return }
      if observedItem.status == .failed {
        DispatchQueue.main.async {
          self.stopPlayback(reason: "error")
        }
      }
    }

    player = queuePlayer
    playerLooper = looper
    currentId = options.id
    currentTitle = options.title
    currentSubtitle = options.subtitle ?? "Mışıl Baby"
    isVipSession = options.isVip
    isPaused = false

    queuePlayer.play()
    updateNowPlayingInfo()

    if !isVipSession {
      let rawRequested = max(0, options.previewBudgetMs ?? Self.freePreviewCapMs)
      let processRemaining = max(0, Self.freePreviewCapMs - cumulativePreviewUsedMs)
      let budget = min(rawRequested, processRemaining)
      if budget <= 0 {
        cumulativePreviewUsedMs = Self.freePreviewCapMs
        stopPlayback(reason: "preview_quota_exhausted")
        return false
      }
      // JS daha düşük bütçe gönderdiyse önceki oturumlardan kullanılan süreyi yüksek su izine (high-water mark) işle
      cumulativePreviewUsedMs = max(cumulativePreviewUsedMs, Self.freePreviewCapMs - budget)
      startPreviewQuota(budgetMs: budget)
    }

    emitState(playing: true, paused: false, id: currentId, reason: "user")
    return true
  }

  private func pausePlayback(reason: String) {
    guard player != nil else { return }
    if !isPaused {
      pausePreviewQuotaAccounting()
    }
    player?.pause()
    isPaused = true
    updateNowPlayingInfo()
    emitState(playing: false, paused: true, id: currentId, reason: reason, previewElapsedMs: currentPreviewElapsedMs())
  }

  private func resumePlaybackFromRemote() {
    guard let p = player else { return }
    if !isVipSession && previewRemainingMs <= 0 {
      return
    }
    p.play()
    isPaused = false
    resumePreviewQuotaAccounting()
    updateNowPlayingInfo()
    emitState(playing: true, paused: false, id: currentId, reason: "remote_play")
  }

  private func stopPlayback(reason: String) {
    if player != nil && !isPaused {
      pausePreviewQuotaAccounting()
    }
    previewTimer?.cancel()
    previewTimer = nil
    statusObservation?.invalidate()
    statusObservation = nil
    player?.pause()
    player = nil
    playerLooper = nil
    let stoppedId = currentId
    currentId = nil
    isPaused = false
    MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
    MPRemoteCommandCenter.shared().playCommand.isEnabled = true
    let elapsed = currentPreviewElapsedMs()
    if !isVipSession && elapsed > 0 {
      cumulativePreviewUsedMs = min(Self.freePreviewCapMs, cumulativePreviewUsedMs + elapsed)
    }
    previewBudgetMs = 0
    previewRemainingMs = 0
    emitState(playing: false, paused: false, id: stoppedId, reason: reason, previewElapsedMs: elapsed)
  }

  // MARK: - Freemium 60sn kota koruması

  private func startPreviewQuota(budgetMs: Double) {
    previewBudgetMs = budgetMs
    previewRemainingMs = budgetMs
    previewLastResumeUptime = ProcessInfo.processInfo.systemUptime
    armPreviewTimer()
  }

  private func armPreviewTimer() {
    previewTimer?.cancel()
    let timer = DispatchSource.makeTimerSource(queue: DispatchQueue.main)
    timer.schedule(deadline: .now() + 0.25, repeating: 0.25)
    timer.setEventHandler { [weak self] in
      self?.tickPreviewQuota()
    }
    previewTimer = timer
    timer.resume()
  }

  private func tickPreviewQuota() {
    guard !isVipSession, player != nil, !isPaused else { return }
    let now = ProcessInfo.processInfo.systemUptime
    let elapsedSinceResume = (now - previewLastResumeUptime) * 1000.0
    let remaining = previewRemainingMs - elapsedSinceResume
    if remaining <= 0 {
      previewRemainingMs = 0
      previewLastResumeUptime = now
      MPRemoteCommandCenter.shared().playCommand.isEnabled = false
      stopPlayback(reason: "preview_quota_exhausted")
    }
  }

  private func pausePreviewQuotaAccounting() {
    guard !isVipSession else { return }
    let now = ProcessInfo.processInfo.systemUptime
    let elapsedSinceResume = (now - previewLastResumeUptime) * 1000.0
    previewRemainingMs = max(0, previewRemainingMs - elapsedSinceResume)
  }

  private func resumePreviewQuotaAccounting() {
    guard !isVipSession else { return }
    previewLastResumeUptime = ProcessInfo.processInfo.systemUptime
  }

  private func currentPreviewElapsedMs() -> Double {
    guard previewBudgetMs > 0 else { return 0 }
    var rem = previewRemainingMs
    if !isVipSession && player != nil && !isPaused {
      let liveDelta = (ProcessInfo.processInfo.systemUptime - previewLastResumeUptime) * 1000.0
      rem = max(0, rem - liveDelta)
    }
    return max(0, min(previewBudgetMs, previewBudgetMs - rem))
  }

  // MARK: - Now Playing / Remote commands

  private func setupRemoteCommands() {
    let center = MPRemoteCommandCenter.shared()

    center.nextTrackCommand.isEnabled = false
    center.previousTrackCommand.isEnabled = false
    center.changePlaybackPositionCommand.isEnabled = false

    center.playCommand.isEnabled = true
    center.playCommand.addTarget { [weak self] _ in
      guard let self = self, self.player != nil else { return .noActionableNowPlayingItem }
      if !self.isVipSession && self.previewRemainingMs <= 0 {
        return .commandFailed
      }
      self.resumePlaybackFromRemote()
      return .success
    }

    center.pauseCommand.isEnabled = true
    center.pauseCommand.addTarget { [weak self] _ in
      guard let self = self, self.player != nil else { return .noActionableNowPlayingItem }
      self.pausePlayback(reason: "remote_pause")
      return .success
    }

    center.togglePlayPauseCommand.isEnabled = true
    center.togglePlayPauseCommand.addTarget { [weak self] _ in
      guard let self = self, self.player != nil else { return .noActionableNowPlayingItem }
      if self.isPaused {
        if !self.isVipSession && self.previewRemainingMs <= 0 { return .commandFailed }
        self.resumePlaybackFromRemote()
      } else {
        self.pausePlayback(reason: "remote_pause")
      }
      return .success
    }

    center.stopCommand.isEnabled = true
    center.stopCommand.addTarget { [weak self] _ in
      guard let self = self, self.player != nil else { return .noActionableNowPlayingItem }
      self.stopPlayback(reason: "remote_stop")
      return .success
    }
  }

  private func updateNowPlayingInfo() {
    var info: [String: Any] = [:]
    info[MPMediaItemPropertyTitle] = currentTitle
    info[MPMediaItemPropertyArtist] = currentSubtitle
    info[MPNowPlayingInfoPropertyIsLiveStream] = true
    info[MPNowPlayingInfoPropertyPlaybackRate] = isPaused ? 0.0 : 1.0

    if let iconImage = UIImage(named: "AppIcon") ?? UIApplication.shared.icon {
      let artwork = MPMediaItemArtwork(boundsSize: iconImage.size) { _ in iconImage }
      info[MPMediaItemPropertyArtwork] = artwork
    }

    MPNowPlayingInfoCenter.default().nowPlayingInfo = info
  }

  private func emitState(playing: Bool, paused: Bool, id: String?, reason: String, previewElapsedMs: Double? = nil) {
    var payload: [String: Any] = [
      "playing": playing,
      "paused": paused,
      "id": id as Any,
      "reason": reason,
    ]
    if let elapsed = previewElapsedMs {
      payload["previewElapsedMs"] = elapsed
    }
    sendEvent("onPlaybackStateChanged", payload)
  }

  // MARK: - Live Sleep (ActivityKit)

  private func resolveDisplayTitle(sleepLabel: String, babyName: String?, showBabyName: Bool) -> String {
    if showBabyName, let name = babyName, !name.isEmpty {
      return "🌙 \(name)"
    }
    return "🌙 \(sleepLabel)"
  }

  private func computeActivityStaleDate(startEpochMs: Double) -> Date {
    let now = Date()
    let maxEnd = Date(timeIntervalSince1970: startEpochMs / 1000.0).addingTimeInterval(Self.activityMaxSleepSeconds)
    let eightHoursFromNow = now.addingTimeInterval(Self.activityStaleAfterSeconds)
    return min(eightHoursFromNow, max(now.addingTimeInterval(60), maxEnd))
  }

  private func hasHealthySystemLiveActivity() -> Bool {
    #if canImport(ActivityKit)
    if #available(iOS 16.2, *) {
      guard let active = Activity<MishilSleepAttributes>.activities.first(where: { $0.activityState == .active }) else {
        return false
      }
      _ = active
      if let createdMs = activityCreatedAtEpochMs {
        let ageMs = Date().timeIntervalSince1970 * 1000.0 - createdMs
        if ageMs >= Self.activityRolloverThresholdMs {
          return false
        }
      }
      return true
    }
    #endif
    return false
  }

  private func handleStartLiveSleep(_ options: StartLiveSleepOptions) -> Bool {
    sleepStartEpochMs = options.startEpochMs
    sleepLabelStore = options.sleepLabel
    sleepSubtitleStore = options.subtitle ?? ""
    sleepBabyName = options.babyName
    sleepShowBabyName = options.showBabyNameOnLockScreen ?? false

    #if canImport(ActivityKit)
    if #available(iOS 16.2, *) {
      let displayTitle = resolveDisplayTitle(sleepLabel: sleepLabelStore, babyName: sleepBabyName, showBabyName: sleepShowBabyName)
      let state = MishilSleepAttributes.ContentState(
        startEpochMs: options.startEpochMs,
        sleepLabel: sleepLabelStore,
        subtitle: sleepSubtitleStore,
        displayTitle: displayTitle
      )
      let staleDate = computeActivityStaleDate(startEpochMs: options.startEpochMs)
      let nowMs = Date().timeIntervalSince1970 * 1000.0
      let existing = Activity<MishilSleepAttributes>.activities
      let activeCandidates = existing.filter { $0.activityState == .active }
      let needsRollover: Bool = {
        guard let createdMs = activityCreatedAtEpochMs else { return false }
        return (nowMs - createdMs) >= Self.activityRolloverThresholdMs
      }()

      if let reusable = activeCandidates.first, !needsRollover {
        Task {
          await reusable.update(ActivityContent(state: state, staleDate: staleDate))
        }
        for extra in existing where extra.id != reusable.id {
          Task { await extra.end(nil, dismissalPolicy: .immediate) }
        }
        if activityCreatedAtEpochMs == nil {
          activityCreatedAtEpochMs = nowMs
        }
        return true
      }

      // Yenileme (7+ saat) veya sistem tarafından sonlandırılmış eski aktivite varsa temizle ve taze 8 saatlik pencere aç
      for old in existing {
        Task { await old.end(nil, dismissalPolicy: .immediate) }
      }

      let attributes = MishilSleepAttributes(sessionId: UUID().uuidString)
      do {
        _ = try Activity.request(
          attributes: attributes,
          content: ActivityContent(state: state, staleDate: staleDate),
          pushType: nil
        )
        activityCreatedAtEpochMs = nowMs
        return true
      } catch {
        return false
      }
    }
    #endif
    return false
  }

  private func handleUpdateLiveSleep(_ options: UpdateLiveSleepOptions) -> Bool {
    sleepStartEpochMs = options.startEpochMs
    if let label = options.sleepLabel { sleepLabelStore = label }
    if let subtitle = options.subtitle { sleepSubtitleStore = subtitle }
    if let name = options.babyName { sleepBabyName = name }
    if let show = options.showBabyNameOnLockScreen { sleepShowBabyName = show }

    #if canImport(ActivityKit)
    if #available(iOS 16.2, *) {
      let displayTitle = resolveDisplayTitle(sleepLabel: sleepLabelStore, babyName: sleepBabyName, showBabyName: sleepShowBabyName)
      let state = MishilSleepAttributes.ContentState(
        startEpochMs: options.startEpochMs,
        sleepLabel: sleepLabelStore,
        subtitle: sleepSubtitleStore,
        displayTitle: displayTitle
      )
      let staleDate = computeActivityStaleDate(startEpochMs: options.startEpochMs)
      let nowMs = Date().timeIntervalSince1970 * 1000.0
      let needsRollover = activityCreatedAtEpochMs != nil && (nowMs - activityCreatedAtEpochMs!) >= Self.activityRolloverThresholdMs
      let activeActivity = Activity<MishilSleepAttributes>.activities.first(where: { $0.activityState == .active })

      if let activity = activeActivity, !needsRollover {
        Task {
          await activity.update(ActivityContent(state: state, staleDate: staleDate))
        }
        return true
      }

      // iOS 8 saat sınırıyla aktiviteyi düşürdüyse ve uygulama ön plandaysa aynı başlangıç saatiyle otomatik yeniden kur
      if UIApplication.shared.applicationState == .active {
        let recreateOptions = StartLiveSleepOptions()
        recreateOptions.startEpochMs = options.startEpochMs
        recreateOptions.sleepLabel = sleepLabelStore
        recreateOptions.subtitle = sleepSubtitleStore
        recreateOptions.babyName = sleepBabyName
        recreateOptions.showBabyNameOnLockScreen = sleepShowBabyName
        return handleStartLiveSleep(recreateOptions)
      }
      return false
    }
    #endif
    return false
  }

  private func handleStopLiveSleep() {
    sleepStartEpochMs = nil
    activityCreatedAtEpochMs = nil
    #if canImport(ActivityKit)
    if #available(iOS 16.2, *) {
      let existing = Activity<MishilSleepAttributes>.activities
      for activity in existing {
        Task { await activity.end(nil, dismissalPolicy: .immediate) }
      }
    }
    #endif
  }

  // MARK: - State snapshot

  private func currentStateDict() -> [String: Any?] {
    let systemSleepHealthy = sleepStartEpochMs != nil && hasHealthySystemLiveActivity()
    return [
      "audioPlaying": player != nil && !isPaused,
      "audioPaused": isPaused,
      "audioId": currentId,
      "previewElapsedMs": currentPreviewElapsedMs(),
      "previewExhausted": !isVipSession && previewBudgetMs > 0 && previewRemainingMs <= 0,
      "sleepActive": systemSleepHealthy,
      "sleepStartEpochMs": systemSleepHealthy ? sleepStartEpochMs : nil,
    ]
  }
}

private extension UIApplication {
  var icon: UIImage? {
    guard
      let iconsDictionary = Bundle.main.infoDictionary?["CFBundleIcons"] as? [String: Any],
      let primaryIconsDictionary = iconsDictionary["CFBundlePrimaryIcon"] as? [String: Any],
      let iconFiles = primaryIconsDictionary["CFBundleIconFiles"] as? [String],
      let lastIcon = iconFiles.last
    else { return nil }
    return UIImage(named: lastIcon)
  }
}
