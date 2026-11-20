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
    public var mode: String
    public var isPaused: Bool
    public var pausedElapsedSec: Int

    public init(
      startEpochMs: Double,
      sleepLabel: String,
      subtitle: String,
      displayTitle: String,
      mode: String = "sleep",
      isPaused: Bool = false,
      pausedElapsedSec: Int = 0
    ) {
      self.startEpochMs = startEpochMs
      self.sleepLabel = sleepLabel
      self.subtitle = subtitle
      self.displayTitle = displayTitle
      self.mode = mode
      self.isPaused = isPaused
      self.pausedElapsedSec = pausedElapsedSec
    }

    enum CodingKeys: String, CodingKey {
      case startEpochMs
      case sleepLabel
      case subtitle
      case displayTitle
      case mode
      case isPaused
      case pausedElapsedSec
    }

    public init(from decoder: Decoder) throws {
      let container = try decoder.container(keyedBy: CodingKeys.self)
      self.startEpochMs = try container.decode(Double.self, forKey: .startEpochMs)
      self.sleepLabel = try container.decode(String.self, forKey: .sleepLabel)
      self.subtitle = try container.decode(String.self, forKey: .subtitle)
      self.displayTitle = try container.decode(String.self, forKey: .displayTitle)
      self.mode = try container.decodeIfPresent(String.self, forKey: .mode) ?? "sleep"
      self.isPaused = try container.decodeIfPresent(Bool.self, forKey: .isPaused) ?? false
      self.pausedElapsedSec = try container.decodeIfPresent(Int.self, forKey: .pausedElapsedSec) ?? 0
    }
  }

  public var sessionId: String

  public init(sessionId: String) {
    self.sessionId = sessionId
  }
}
#endif
