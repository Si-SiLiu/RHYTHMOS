import Foundation

/// A user-authored, local-only daily check-in. It is intentionally separate
/// from imported health measurements and desktop-derived readiness values.
struct DailyCheckIn: Codable, Equatable, Identifiable, Sendable {
    let date: Date
    let perceivedRecovery: PerceivedRecovery
    let trainingIntent: TrainingIntent
    let note: String?
    let updatedAt: Date

    var id: Date { date }
}

enum PerceivedRecovery: String, CaseIterable, Codable, Hashable, Sendable {
    case low
    case moderate
    case good

    var title: String {
        switch self {
        case .low: return "偏低"
        case .moderate: return "一般"
        case .good: return "良好"
        }
    }

    var score: Int {
        switch self {
        case .low: return 1
        case .moderate: return 2
        case .good: return 3
        }
    }
}

enum TrainingIntent: String, CaseIterable, Codable, Hashable, Sendable {
    case rest
    case light
    case normal

    var title: String {
        switch self {
        case .rest: return "休息"
        case .light: return "轻度"
        case .normal: return "正常"
        }
    }
}
