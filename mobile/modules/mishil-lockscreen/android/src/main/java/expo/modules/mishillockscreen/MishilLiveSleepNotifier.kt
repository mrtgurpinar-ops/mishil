package expo.modules.mishillockscreen

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat

object MishilLiveSleepNotifier {
  private const val CHANNEL_ID = "live_sleep_channel"
  private const val NOTIFICATION_ID = 7302
  private const val MISHIL_AMBER_COLOR = 0xFFE8A855.toInt()

  private fun ensureChannel(context: Context) {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
      val manager = context.getSystemService(NotificationManager::class.java)
      if (manager.getNotificationChannel(CHANNEL_ID) == null) {
        val channel = NotificationChannel(CHANNEL_ID, "Canlı Uyku Takibi", NotificationManager.IMPORTANCE_LOW).apply {
          lockscreenVisibility = android.app.Notification.VISIBILITY_PUBLIC
          setShowBadge(false)
          enableVibration(false)
          setSound(null, null)
        }
        manager.createNotificationChannel(channel)
      }
    }
  }

  private fun contentIntent(context: Context): PendingIntent {
    val deepLinkIntent = Intent(Intent.ACTION_VIEW, Uri.parse("misilbaby://sleep")).apply {
      setPackage(context.packageName)
    }
    val resolvedIntent = if (deepLinkIntent.resolveActivity(context.packageManager) != null) {
      deepLinkIntent
    } else {
      context.packageManager.getLaunchIntentForPackage(context.packageName) ?: deepLinkIntent
    }
    return PendingIntent.getActivity(
      context, 0, resolvedIntent,
      PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
    )
  }

  fun show(context: Context, startEpochMs: Long, title: String, subtitle: String) {
    ensureChannel(context)
    val builder = NotificationCompat.Builder(context, CHANNEL_ID)
      .setContentTitle(title)
      .setContentText(subtitle)
      .setSmallIcon(android.R.drawable.ic_menu_recent_history)
      .setColor(MISHIL_AMBER_COLOR)
      .setOngoing(true)
      .setShowWhen(true)
      .setWhen(startEpochMs)
      .setUsesChronometer(true)
      .setOnlyAlertOnce(true)
      .setCategory(NotificationCompat.CATEGORY_STOPWATCH)
      .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
      .setContentIntent(contentIntent(context))

    applyApi36LiveUpdate(builder)

    try {
      NotificationManagerCompat.from(context).notify(NOTIFICATION_ID, builder.build())
    } catch (e: SecurityException) {}
  }

  fun cancel(context: Context) {
    try {
      NotificationManagerCompat.from(context).cancel(NOTIFICATION_ID)
    } catch (e: Exception) {}
  }

  // Android 16 (API 36) durum çubuğu "Live Update" chip desteği — eski sürümlerde sessizce yoksayılır
  private fun applyApi36LiveUpdate(builder: NotificationCompat.Builder) {
    if (Build.VERSION.SDK_INT < 36) return
    try {
      builder.extras.putBoolean("android.requestPromotedOngoing", true)
      val method = builder.javaClass.methods.firstOrNull { it.name == "setRequestPromotedOngoing" }
      method?.invoke(builder, true)
    } catch (e: Exception) {
      // Reflection yolu başarısız olsa bile standart kronometre bildirimi çalışmaya devam eder
    }
  }
}
