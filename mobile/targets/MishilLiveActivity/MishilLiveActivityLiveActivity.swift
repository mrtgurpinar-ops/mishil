import ActivityKit
import WidgetKit
import SwiftUI

private let mishilOledBackground = Color(red: 11 / 255, green: 15 / 255, blue: 26 / 255)
private let mishilAmberAccent = Color(red: 232 / 255, green: 168 / 255, blue: 85 / 255)
private let mishilMaxSleepSeconds: Double = 16 * 3600

@available(iOS 16.2, *)
private func sleepTimerRange(startEpochMs: Double) -> ClosedRange<Date> {
  let start = Date(timeIntervalSince1970: startEpochMs / 1000.0)
  let end = start.addingTimeInterval(mishilMaxSleepSeconds)
  return start...end
}

@available(iOS 16.2, *)
struct MishilSleepLiveActivity: Widget {
  var body: some WidgetConfiguration {
    ActivityConfiguration(for: MishilSleepAttributes.self) { context in
      MishilSleepLockScreenView(state: context.state, isStale: context.isStale)
        .widgetURL(URL(string: "misilbaby://sleep"))
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
          Text(timerInterval: sleepTimerRange(startEpochMs: context.state.startEpochMs), countsDown: false)
            .monospacedDigit()
            .font(.title3.weight(.bold))
            .foregroundColor(.white)
        }
        DynamicIslandExpandedRegion(.bottom) {
          Text(context.state.subtitle)
            .font(.caption)
            .foregroundColor(.gray)
        }
      } compactLeading: {
        Text("🌙")
          .foregroundColor(mishilAmberAccent)
      } compactTrailing: {
        Text(timerInterval: sleepTimerRange(startEpochMs: context.state.startEpochMs), countsDown: false)
          .monospacedDigit()
          .frame(maxWidth: 56)
          .foregroundColor(.white)
      } minimal: {
        Text("🌙")
          .foregroundColor(mishilAmberAccent)
      }
      .widgetURL(URL(string: "misilbaby://sleep"))
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
      // 8 saati aşan gece uykularında kilit ekranı kartı (8–12 saat aralığı) açık kaldığı sürece OS sayacı kesintisiz akar
      Text(timerInterval: sleepTimerRange(startEpochMs: state.startEpochMs), countsDown: false)
        .monospacedDigit()
        .font(.title2.weight(.bold))
        .foregroundColor(.white.opacity(isLuminanceReduced ? 0.85 : 1.0))
    }
    .padding(16)
    .background(mishilOledBackground)
  }
}
