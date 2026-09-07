import Foundation

struct DailySnapshot: Equatable, Sendable {
    let date: Date
    let recovery: RecoverySummary
    let recoveryDetails: RecoveryDetails
    let sleep: MetricValue
    let sleepDetails: SleepDetails
    let hrv: MetricValue
    let restingHeartRate: MetricValue
    let training: TrainingSummary
    let nextAction: String
}

struct RecoverySummary: Equatable, Sendable {
    let status: ReadinessStatus
    let confidence: DataConfidence
    let explanation: String
}

enum ReadinessStatus: String, CaseIterable, Sendable {
    case ready
    case steady
    case conserve
    case insufficientData = "insufficient_data"

    var title: String {
        switch self {
        case .ready: return "准备充分"
        case .steady: return "保持节奏"
        case .conserve: return "建议保守"
        case .insufficientData: return "数据尚不足"
        }
    }

    var systemImage: String {
        switch self {
        case .ready: return "checkmark.circle.fill"
        case .steady: return "equal.circle.fill"
        case .conserve: return "exclamationmark.circle.fill"
        case .insufficientData: return "questionmark.circle.fill"
        }
    }
}

enum DataConfidence: String, Sendable {
    case high
    case medium
    case building
    case low
    case veryLow = "very_low"

    var title: String {
        switch self {
        case .high: return "数据充分"
        case .medium: return "数据适中"
        case .building: return "基线建立中"
        case .low: return "数据有限"
        case .veryLow: return "数据很有限"
        }
    }
}

struct RecoveryDetails: Equatable, Sendable {
    let score: Double?
    let scoreVersion: String?
    let confidenceScore: Double?
    let confidence: DataConfidence
    let confidenceVersion: String?
    let missingGroups: [String]
    let morningHRV: DetailMetric
    let morningRestingHeartRate: DetailMetric
}

struct SleepDetails: Equatable, Sendable {
    let duration: DetailMetric
    let score: DetailMetric
    let nightlyHRV: DetailMetric
    let restingHeartRate: DetailMetric
    let respirationRate: DetailMetric
}

struct DetailMetric: Equatable, Sendable, Identifiable {
    let id: String
    let label: String
    let value: String
    let rawValue: Double?
    let provenance: MetricProvenance
}

struct MetricProvenance: Equatable, Sendable {
    let source: String
    let isFallback: Bool
    let isManualOverride: Bool
    let reason: String
}

struct MetricValue: Equatable, Sendable, Identifiable {
    let id: String
    let label: String
    let value: String
    let detail: String
    let state: MetricState
}

struct TrainingSummary: Equatable, Sendable {
    let sessionCount: Int
    let durationMinutes: Double?
    let caloriesKcal: Double?
    let sports: [String]

    var hasActivity: Bool {
        sessionCount > 0 || durationMinutes != nil || caloriesKcal != nil
    }
}

enum MetricState: Sendable {
    case neutral
    case supportive
    case caution
    case unavailable
}
