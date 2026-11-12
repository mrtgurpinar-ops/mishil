import Foundation

#if canImport(ActivityKit)
import ActivityKit

@available(iOS 16.1, *)
public struct MishilSleepAttributes: ActivityAttributes {
  public struct ContentState: Codable, Hashable {
    public var startEpochMs: Double
    public var sleepLabel: String
    public var subtitle: String
    public var displayTitle: String

    public init(startEpochMs: Double, sleepLabel: String, subtitle: String, displayTitle: String) {
      self.startEpochMs = startEpochMs
      self.sleepLabel = sleepLabel
      self.subtitle = subtitle
      self.displayTitle = displayTitle
    }
  }

  public var sessionId: String

  public init(sessionId: String) {
    self.sessionId = sessionId
  }
}
#endif
