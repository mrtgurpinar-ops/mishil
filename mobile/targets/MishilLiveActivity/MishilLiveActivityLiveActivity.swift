import ActivityKit
import WidgetKit
import SwiftUI

private let mishilOledBackground = Color(red: 11 / 255, green: 15 / 255, blue: 26 / 255)
private let mishilAmberAccent = Color(red: 232 / 255, green: 168 / 255, blue: 85 / 255)
private let mishilMaxSleepSeconds: Double = 16 * 3600
private let mishilMaxNursingSeconds: Double = 3 * 3600

@available(iOS 16.2, *)
private func activityTimerRange(state: MishilSleepAttributes.ContentState) -> ClosedRange<Date> {
  let maxSeconds = state.mode == "nursing" ? mishilMaxNursingSeconds : mishilMaxSleepSeconds
  let start = Date(timeIntervalSince1970: state.startEpochMs / 1000.0)
  let end = start.addingTimeInterval(maxSeconds)
  return start...end
}

@available(iOS 16.2, *)
private func activityLeadEmoji(state: MishilSleepAttributes.ContentState) -> String {
  return state.mode == "nursing" ? "🤱" : "🌙"
}

@available(iOS 16.2, *)
private func activityDeepLinkURL(state: MishilSleepAttributes.ContentState) -> URL? {
  return URL(string: state.mode == "nursing" ? "misilbaby://nursing" : "misilbaby://sleep")
}

@available(iOS 16.2, *)
private func formatPausedElapsed(_ rawSec: Int) -> String {
  let sec = max(0, rawSec)
  let hrs = sec / 3600
  let mins = (sec % 3600) / 60
  let secs = sec % 60
  if hrs > 0 {
    return String(format: "%02d:%02d:%02d ⏸", hrs, mins, secs)
  }
  return String(format: "%02d:%02d ⏸", mins, secs)
}

@available(iOS 16.2, *)
struct MishilSleepLiveActivity: Widget {
  var body: some WidgetConfiguration {
    ActivityConfiguration(for: MishilSleepAttributes.self) { context in
      MishilSleepLockScreenView(state: context.state, isStale: context.isStale)
        .widgetURL(activityDeepLinkURL(state: context.state))
        .activityBackgroundTint(mishilOledBackground)
        .activitySystemActionForegroundColor(mishilAmberAccent)
    } dynamicIsland: { context in
      DynamicIsland {
        DynamicIslandExpandedRegion(.leading) {
          Text(context.state.displayTitle)
            .font(.subheadline.weight(.semibold))
            .foregroundColor(mishilAmberAccent)
        }
        DynamicIslandExpandedRegion(.trailing) {
          if context.state.isPaused {
            Text(formatPausedElapsed(context.state.pausedElapsedSec))
              .monospacedDigit()
              .font(.title3.weight(.bold))
              .foregroundColor(mishilAmberAccent)
          } else {
            Text(timerInterval: activityTimerRange(state: context.state), countsDown: false)
              .monospacedDigit()
              .font(.title3.weight(.bold))
              .foregroundColor(.white)
          }
        }
        DynamicIslandExpandedRegion(.bottom) {
          Text(context.state.subtitle)
            .font(.caption)
            .foregroundColor(.gray)
        }
      } compactLeading: {
        Text(activityLeadEmoji(state: context.state))
          .foregroundColor(mishilAmberAccent)
      } compactTrailing: {
        if context.state.isPaused {
          Text(formatPausedElapsed(context.state.pausedElapsedSec))
            .monospacedDigit()
            .frame(maxWidth: 64)
            .foregroundColor(mishilAmberAccent)
        } else {
          Text(timerInterval: activityTimerRange(state: context.state), countsDown: false)
            .monospacedDigit()
            .frame(maxWidth: 56)
            .foregroundColor(.white)
        }
      } minimal: {
        Text(activityLeadEmoji(state: context.state))
          .foregroundColor(mishilAmberAccent)
      }
      .widgetURL(activityDeepLinkURL(state: context.state))
    }
  }
}

@available(iOS 16.2, *)
private struct MishilSleepLockScreenView: View {
  @Environment(\.isLuminanceReduced) var isLuminanceReduced
  let state: MishilSleepAttributes.ContentState
  let isStale: Bool

  var body: some View {
    HStack(spacing: 12) {
      VStack(alignment: .leading, spacing: 4) {
        Text(state.displayTitle)
          .font(.headline)
          .foregroundColor(mishilAmberAccent.opacity(isLuminanceReduced ? 0.75 : 1.0))
        Text(state.subtitle)
          .font(.caption)
          .foregroundColor(.gray.opacity(isStale ? 0.75 : 1.0))
      }
      Spacer()
      if state.isPaused {
        Text(formatPausedElapsed(state.pausedElapsedSec))
          .monospacedDigit()
          .font(.title2.weight(.bold))
          .foregroundColor(mishilAmberAccent.opacity(isLuminanceReduced ? 0.85 : 1.0))
      } else {
        // 8 saati aşan gece uykularında kilit ekranı kartı açık kaldığı sürece OS sayacı kesintisiz akar
        Text(timerInterval: activityTimerRange(state: state), countsDown: false)
          .monospacedDigit()
          .font(.title2.weight(.bold))
          .foregroundColor(.white.opacity(isLuminanceReduced ? 0.85 : 1.0))
      }
    }
    .padding(16)
    .background(mishilOledBackground)
  }
}
