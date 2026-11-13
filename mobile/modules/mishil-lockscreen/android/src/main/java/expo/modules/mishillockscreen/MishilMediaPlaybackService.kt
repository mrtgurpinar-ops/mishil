package expo.modules.mishillockscreen

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.os.Binder
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.SystemClock
import android.support.v4.media.session.MediaSessionCompat
import android.support.v4.media.session.PlaybackStateCompat
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.media.session.MediaButtonReceiver

class MishilMediaPlaybackService : Service() {

  companion object {
    const val CHANNEL_ID = "lullaby_playback_channel"
    const val NOTIFICATION_ID = 7301
    const val ACTION_STOP = "expo.modules.mishillockscreen.ACTION_STOP"
    const val FREE_PREVIEW_CAP_MS = 60000L
  }

  interface PlaybackListener {
    fun onPlaybackStateChanged(playing: Boolean, paused: Boolean, id: String?, reason: String, previewElapsedMs: Long?)
  }

  private val binder = LocalBinder()
  private var mediaPlayer: MediaPlayer? = null
  private var mediaSession: MediaSessionCompat? = null

  private var currentId: String? = null
  private var currentTitle: String = ""
  private var currentSubtitle: String = "Mışıl Baby"
  private var isVip: Boolean = true
  private var isPaused: Boolean = false

  private var cumulativePreviewUsedMs: Long = 0
  private var previewBudgetMs: Long = 0
  private var previewRemainingMs: Long = 0
  private var previewLastResumeElapsed: Long = 0
  private val handler = Handler(Looper.getMainLooper())
  private var previewRunnable: Runnable? = null

  var listener: PlaybackListener? = null

  inner class LocalBinder : Binder() {
    fun getService(): MishilMediaPlaybackService = this@MishilMediaPlaybackService
  }

  override fun onBind(intent: Intent?): IBinder = binder

  override fun onCreate() {
    super.onCreate()
    ensureNotificationChannel()
    mediaSession = MediaSessionCompat(this, "MishilLockScreen").apply {
      setCallback(object : MediaSessionCompat.Callback() {
        override fun onPlay() { handleRemotePlay() }
        override fun onPause() { handleRemotePause() }
        override fun onStop() { handleRemoteStop() }
      })
      isActive = true
    }
  }

  override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
    mediaSession?.let { MediaButtonReceiver.handleIntent(it, intent) }
    if (intent?.action == ACTION_STOP) {
      stopPlayback("user")
    }
    return START_NOT_STICKY
  }

  private fun ensureNotificationChannel() {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
      val manager = getSystemService(NotificationManager::class.java)
      if (manager.getNotificationChannel(CHANNEL_ID) == null) {
        val channel = NotificationChannel(CHANNEL_ID, "Ninni Çalma", NotificationManager.IMPORTANCE_LOW).apply {
          lockscreenVisibility = Notification.VISIBILITY_PUBLIC
          setShowBadge(false)
        }
        manager.createNotificationChannel(channel)
      }
    }
  }

  fun playAudio(id: String, url: String, title: String, subtitle: String?, volume: Float?, isVipFlag: Boolean, previewBudgetMsArg: Long?) {
    if (mediaPlayer != null && !isVip) {
      if (!isPaused) pausePreviewAccounting()
      val switchedSessionUsedMs = currentPreviewElapsedMs()
      cumulativePreviewUsedMs = (cumulativePreviewUsedMs + switchedSessionUsedMs).coerceAtMost(FREE_PREVIEW_CAP_MS)
      previewBudgetMs = 0
      previewRemainingMs = 0
      listener?.onPlaybackStateChanged(false, false, currentId, "track_switch", switchedSessionUsedMs)
    }
    stopPreviewTimer()
    releasePlayer()
    currentId = id
    currentTitle = title
    currentSubtitle = subtitle ?: "Mışıl Baby"
    isVip = isVipFlag
    isPaused = false

    try {
      mediaPlayer = MediaPlayer().apply {
        setAudioAttributes(
          AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_MEDIA)
            .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
            .build()
        )
        isLooping = true
        setDataSource(url)
        val vol = (volume ?: 1f).coerceIn(0f, 1f)
        setVolume(vol, vol)
        setOnPreparedListener {
          if (!isVip && !isPaused) {
            previewLastResumeElapsed = SystemClock.elapsedRealtime()
          }
          it.start()
          startForegroundSafely()
          updateMediaSessionState()
          updateNotification()
          listener?.onPlaybackStateChanged(true, false, currentId, "user", null)
        }
        setOnErrorListener { _, _, _ ->
          listener?.onPlaybackStateChanged(false, false, currentId, "error", null)
          stopPlaybackInternal()
          true
        }
        prepareAsync()
      }
    } catch (e: Exception) {
      listener?.onPlaybackStateChanged(false, false, currentId, "error", null)
      return
    }

    if (!isVip) {
      val rawRequested = (previewBudgetMsArg ?: FREE_PREVIEW_CAP_MS).coerceAtLeast(0L)
      val processRemaining = (FREE_PREVIEW_CAP_MS - cumulativePreviewUsedMs).coerceAtLeast(0L)
      val budget = minOf(rawRequested, processRemaining)
      if (budget <= 0) {
        cumulativePreviewUsedMs = FREE_PREVIEW_CAP_MS
        stopPlayback("preview_quota_exhausted")
        return
      }
      cumulativePreviewUsedMs = maxOf(cumulativePreviewUsedMs, FREE_PREVIEW_CAP_MS - budget)
      previewBudgetMs = budget
      previewRemainingMs = budget
      previewLastResumeElapsed = SystemClock.elapsedRealtime()
      armPreviewTimer()
    }
  }

  fun pauseAudio(reason: String = "user") {
    val player = mediaPlayer ?: return
    if (!isPaused) pausePreviewAccounting()
    if (player.isPlaying) player.pause()
    isPaused = true
    updateMediaSessionState()
    updateNotification()
    listener?.onPlaybackStateChanged(false, true, currentId, reason, currentPreviewElapsedMs())
  }

  fun resumeAudio(reason: String = "remote_play"): Boolean {
    val player = mediaPlayer ?: return false
    if (!isVip && previewRemainingMs <= 0) return false
    player.start()
    isPaused = false
    resumePreviewAccounting()
    updateMediaSessionState()
    updateNotification()
    listener?.onPlaybackStateChanged(true, false, currentId, reason, null)
    return true
  }

  fun stopPlayback(reason: String) {
    if (mediaPlayer != null && !isPaused) {
      pausePreviewAccounting()
    }
    val elapsed = currentPreviewElapsedMs()
    if (!isVip && elapsed > 0) {
      cumulativePreviewUsedMs = (cumulativePreviewUsedMs + elapsed).coerceAtMost(FREE_PREVIEW_CAP_MS)
    }
    previewBudgetMs = 0
    previewRemainingMs = 0
    val stoppedId = currentId
    stopPlaybackInternal()
    listener?.onPlaybackStateChanged(false, false, stoppedId, reason, elapsed)
  }

  private fun stopPlaybackInternal() {
    stopPreviewTimer()
    releasePlayer()
    currentId = null
    isPaused = false
    mediaSession?.setPlaybackState(
      PlaybackStateCompat.Builder()
        .setState(PlaybackStateCompat.STATE_STOPPED, 0, 1f)
        .build()
    )
    stopForegroundSafely()
  }

  fun setVolume(volume: Float) {
    val v = volume.coerceIn(0f, 1f)
    mediaPlayer?.setVolume(v, v)
  }

  fun getStateSnapshot(): Map<String, Any?> {
    return mapOf(
      "audioPlaying" to (mediaPlayer != null && !isPaused),
      "audioPaused" to isPaused,
      "audioId" to currentId,
      "previewElapsedMs" to currentPreviewElapsedMs(),
      "previewExhausted" to (!isVip && previewBudgetMs > 0 && previewRemainingMs <= 0)
    )
  }

  private fun handleRemotePlay() {
    if (!resumeAudio("remote_play")) {
      listener?.onPlaybackStateChanged(false, false, currentId, "preview_quota_exhausted", currentPreviewElapsedMs())
    }
  }

  private fun handleRemotePause() = pauseAudio("remote_pause")

  private fun handleRemoteStop() = stopPlayback("remote_stop")

  // MARK: Freemium 60sn kota koruması — SystemClock.elapsedRealtime() monotonik, duvar saati manipülasyonuna dayanıklı
  private fun armPreviewTimer() {
    stopPreviewTimer()
    previewRunnable = object : Runnable {
      override fun run() {
        tickPreviewQuota()
        if (previewRunnable != null) handler.postDelayed(this, 250)
      }
    }
    handler.postDelayed(previewRunnable!!, 250)
  }

  private fun stopPreviewTimer() {
    previewRunnable?.let { handler.removeCallbacks(it) }
    previewRunnable = null
  }

  private fun tickPreviewQuota() {
    if (isVip || mediaPlayer == null || isPaused) return
    val now = SystemClock.elapsedRealtime()
    val elapsedSinceResume = now - previewLastResumeElapsed
    val remaining = previewRemainingMs - elapsedSinceResume
    if (remaining <= 0) {
      previewRemainingMs = 0
      previewLastResumeElapsed = now
      stopPlayback("preview_quota_exhausted")
    }
  }

  private fun pausePreviewAccounting() {
    if (isVip) return
    val now = SystemClock.elapsedRealtime()
    previewRemainingMs = (previewRemainingMs - (now - previewLastResumeElapsed)).coerceAtLeast(0)
  }

  private fun resumePreviewAccounting() {
    if (isVip) return
    previewLastResumeElapsed = SystemClock.elapsedRealtime()
  }

  private fun currentPreviewElapsedMs(): Long {
    if (previewBudgetMs <= 0) return 0
    var rem = previewRemainingMs
    if (!isVip && mediaPlayer != null && !isPaused) {
      val liveDelta = SystemClock.elapsedRealtime() - previewLastResumeElapsed
      rem = (rem - liveDelta).coerceAtLeast(0)
    }
    return (previewBudgetMs - rem).coerceIn(0, previewBudgetMs)
  }

  private fun updateMediaSessionState() {
    val state = if (mediaPlayer != null && !isPaused) PlaybackStateCompat.STATE_PLAYING else PlaybackStateCompat.STATE_PAUSED
    mediaSession?.setPlaybackState(
      PlaybackStateCompat.Builder()
        .setActions(
          PlaybackStateCompat.ACTION_PLAY or
            PlaybackStateCompat.ACTION_PAUSE or
            PlaybackStateCompat.ACTION_PLAY_PAUSE or
            PlaybackStateCompat.ACTION_STOP
        )
        .setState(state, 0, if (state == PlaybackStateCompat.STATE_PLAYING) 1f else 0f)
        .build()
    )
  }

  private fun startForegroundSafely() {
    try {
      val notification = buildNotification()
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
        startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK)
      } else {
        startForeground(NOTIFICATION_ID, notification)
      }
    } catch (e: SecurityException) {
      // Android 12+ arka plandan foreground servis başlatma kısıtlaması — sessizce geç
    } catch (e: IllegalStateException) {
      // Çok benzer kısıtlama senaryosu
    }
  }

  private fun stopForegroundSafely() {
    try {
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
        stopForeground(STOP_FOREGROUND_REMOVE)
      } else {
        @Suppress("DEPRECATION")
        stopForeground(true)
      }
    } catch (e: Exception) {}
  }

  private fun updateNotification() {
    if (mediaPlayer == null) return
    try {
      val manager = NotificationManagerCompat.from(this)
      manager.notify(NOTIFICATION_ID, buildNotification())
    } catch (e: SecurityException) {}
  }

  private fun buildNotification(): Notification {
    val session = mediaSession
    val playPauseAction = if (!isPaused) {
      NotificationCompat.Action(
        android.R.drawable.ic_media_pause,
        "Duraklat",
        MediaButtonReceiver.buildMediaButtonPendingIntent(this, PlaybackStateCompat.ACTION_PAUSE)
      )
    } else {
      NotificationCompat.Action(
        android.R.drawable.ic_media_play,
        "Oynat",
        MediaButtonReceiver.buildMediaButtonPendingIntent(this, PlaybackStateCompat.ACTION_PLAY)
      )
    }
    val stopAction = NotificationCompat.Action(
      android.R.drawable.ic_media_pause,
      "Durdur",
      MediaButtonReceiver.buildMediaButtonPendingIntent(this, PlaybackStateCompat.ACTION_STOP)
    )

    val contentIntent = packageManager.getLaunchIntentForPackage(packageName)?.apply {
      addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP)
    }?.let {
      PendingIntent.getActivity(this, 0, it, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    }

    return NotificationCompat.Builder(this, CHANNEL_ID)
      .setContentTitle(currentTitle)
      .setContentText(currentSubtitle)
      .setSmallIcon(android.R.drawable.ic_media_play)
      .setOngoing(!isPaused)
      .setOnlyAlertOnce(true)
      .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
      .setContentIntent(contentIntent)
      .addAction(playPauseAction)
      .addAction(stopAction)
      .setStyle(
        androidx.media.app.NotificationCompat.MediaStyle()
          .setMediaSession(session?.sessionToken)
          .setShowActionsInCompactView(0, 1)
      )
      .build()
  }

  private fun releasePlayer() {
    mediaPlayer?.let {
      try { if (it.isPlaying) it.stop() } catch (e: Exception) {}
      try { it.release() } catch (e: Exception) {}
    }
    mediaPlayer = null
  }

  override fun onDestroy() {
    stopPreviewTimer()
    releasePlayer()
    mediaSession?.release()
    super.onDestroy()
  }
}
