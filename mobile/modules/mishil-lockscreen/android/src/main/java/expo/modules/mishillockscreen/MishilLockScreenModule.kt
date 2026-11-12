package expo.modules.mishillockscreen

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.os.IBinder
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import expo.modules.kotlin.records.Field
import expo.modules.kotlin.records.Record

class PlayAudioOptions : Record {
  @Field var id: String = ""
  @Field var url: String = ""
  @Field var title: String = ""
  @Field var subtitle: String? = null
  @Field var volume: Double? = null
  @Field var isVip: Boolean = false
  @Field var previewBudgetMs: Double? = null
}

class StartLiveSleepOptions : Record {
  @Field var startEpochMs: Double = 0.0
  @Field var sleepLabel: String = ""
  @Field var subtitle: String? = null
  @Field var babyName: String? = null
  @Field var showBabyNameOnLockScreen: Boolean? = null
  @Field var lang: String? = null
}

class UpdateLiveSleepOptions : Record {
  @Field var startEpochMs: Double = 0.0
  @Field var sleepLabel: String? = null
  @Field var subtitle: String? = null
  @Field var babyName: String? = null
  @Field var showBabyNameOnLockScreen: Boolean? = null
}

class MishilLockScreenModule : Module() {
  private var boundService: MishilMediaPlaybackService? = null
  private var isBound = false
  private var pendingPlayOptions: PlayAudioOptions? = null

  private var sleepStartEpochMs: Double? = null
  private var sleepLabelStore: String = ""
  private var sleepSubtitleStore: String = ""
  private var sleepBabyName: String? = null
  private var sleepShowBabyName: Boolean = false

  private val serviceConnection = object : ServiceConnection {
    override fun onServiceConnected(name: ComponentName?, binder: IBinder?) {
      val service = (binder as? MishilMediaPlaybackService.LocalBinder)?.getService()
      boundService = service
      isBound = true
      service?.listener = object : MishilMediaPlaybackService.PlaybackListener {
        override fun onPlaybackStateChanged(playing: Boolean, paused: Boolean, id: String?, reason: String, previewElapsedMs: Long?) {
          val payload = mutableMapOf<String, Any?>(
            "playing" to playing,
            "paused" to paused,
            "id" to id,
            "reason" to reason
          )
          if (previewElapsedMs != null) payload["previewElapsedMs"] = previewElapsedMs.toDouble()
          sendEvent("onPlaybackStateChanged", payload)
        }
      }
      val pending = pendingPlayOptions
      if (pending != null && service != null) {
        pendingPlayOptions = null
        service.playAudio(
          pending.id,
          pending.url,
          pending.title,
          pending.subtitle,
          pending.volume?.toFloat(),
          pending.isVip,
          pending.previewBudgetMs?.toLong()
        )
      }
    }

    override fun onServiceDisconnected(name: ComponentName?) {
      boundService = null
      isBound = false
    }
  }

  private val context: Context
    get() = appContext.reactContext ?: throw IllegalStateException("React context unavailable")

  private fun ensureBound() {
    if (isBound) return
    val intent = Intent(context, MishilMediaPlaybackService::class.java)
    context.bindService(intent, serviceConnection, Context.BIND_AUTO_CREATE)
  }

  override fun definition() = ModuleDefinition {
    Name("MishilLockScreen")

    Events("onPlaybackStateChanged")

    OnCreate {
      ensureBound()
    }

    AsyncFunction("playAudio") { options: PlayAudioOptions ->
      if (!options.isVip && (options.previewBudgetMs ?: 0.0) <= 0.0) {
        return@AsyncFunction false
      }
      ensureBound()
      val intent = Intent(context, MishilMediaPlaybackService::class.java)
      try {
        context.startService(intent)
      } catch (e: Exception) {
        // Arka plandan geç başlatma durumlarında bağlı servis üzerinden devam et
      }
      val svc = boundService
      if (svc != null) {
        svc.playAudio(
          options.id,
          options.url,
          options.title,
          options.subtitle,
          options.volume?.toFloat(),
          options.isVip,
          options.previewBudgetMs?.toLong()
        )
      } else {
        pendingPlayOptions = options
      }
      true
    }

    AsyncFunction("pauseAudio") {
      pendingPlayOptions = null
      boundService?.pauseAudio("user")
    }

    AsyncFunction("stopAudio") {
      pendingPlayOptions = null
      boundService?.stopPlayback("user")
    }

    AsyncFunction("setAudioVolume") { volume: Double ->
      boundService?.setVolume(volume.toFloat())
    }

    AsyncFunction("startLiveSleep") { options: StartLiveSleepOptions ->
      sleepStartEpochMs = options.startEpochMs
      sleepLabelStore = options.sleepLabel
      sleepSubtitleStore = options.subtitle ?: ""
      sleepBabyName = options.babyName
      sleepShowBabyName = options.showBabyNameOnLockScreen ?: false
      MishilLiveSleepNotifier.show(context, options.startEpochMs.toLong(), resolveDisplayTitle(), sleepSubtitleStore)
      true
    }

    AsyncFunction("updateLiveSleep") { options: UpdateLiveSleepOptions ->
      sleepStartEpochMs = options.startEpochMs
      options.sleepLabel?.let { sleepLabelStore = it }
      options.subtitle?.let { sleepSubtitleStore = it }
      options.babyName?.let { sleepBabyName = it }
      options.showBabyNameOnLockScreen?.let { sleepShowBabyName = it }
      MishilLiveSleepNotifier.show(context, options.startEpochMs.toLong(), resolveDisplayTitle(), sleepSubtitleStore)
      true
    }

    AsyncFunction("stopLiveSleep") {
      sleepStartEpochMs = null
      MishilLiveSleepNotifier.cancel(context)
    }

    AsyncFunction("getLockScreenState") {
      val base = boundService?.getStateSnapshot() ?: mapOf(
        "audioPlaying" to false,
        "audioPaused" to false,
        "audioId" to null,
        "previewElapsedMs" to 0.0,
        "previewExhausted" to false
      )
      base + mapOf(
        "sleepActive" to (sleepStartEpochMs != null),
        "sleepStartEpochMs" to sleepStartEpochMs
      )
    }

    OnDestroy {
      if (isBound) {
        try { context.unbindService(serviceConnection) } catch (e: Exception) {}
        isBound = false
      }
    }
  }

  private fun resolveDisplayTitle(): String {
    return if (sleepShowBabyName && !sleepBabyName.isNullOrEmpty()) {
      "🌙 $sleepBabyName"
    } else {
      "🌙 $sleepLabelStore"
    }
  }
}
