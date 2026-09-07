import Foundation

struct DailySnapshot: Equatable, Sendable {
    let date: Date
    let recovery: RecoverySummary
    let sleep: MetricValue
    let hrv: MetricValue
    let restingHeartRate: MetricValue
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

    var title: String {
        switch self {
        case .high: return "数据充分"
        case .medium: return "数据适中"
        case .building: return "基线建立中"
        case .low: return "数据有限"
        }
    }
}

struct MetricValue: Equatable, Sendable, Identifiable {
    let id: String
    let label: String
    let value: String
    let detail: String
    let state: MetricState
}

enum MetricState: Sendable {
    case neutral
    case supportive
    case caution
    case unavailable
}
