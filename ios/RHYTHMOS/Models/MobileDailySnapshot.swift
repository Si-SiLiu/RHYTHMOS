import Foundation

/// Codable representation of `rhythmos.mobile_daily_snapshot` v1.
/// It is a projection, never a copy of the desktop SQLite database.
struct MobileDailySnapshot: Decodable, Sendable {
    let kind: String
    let version: Int
    let generatedAt: String
    let date: String
    let recovery: Recovery
    let sleep: Sleep
    let training: Training

    enum CodingKeys: String, CodingKey {
        case kind, version, date, recovery, sleep, training
        case generatedAt = "generated_at"
    }

    struct Recovery: Decodable, Sendable {
        let status: String
        let score: Double?
        let scoreVersion: String?
        let recommendationCode: String?
        let confidence: Confidence?
        let morningHRV: MobileMetric
        let morningRestingHeartRate: MobileMetric

        enum CodingKeys: String, CodingKey {
            case status, score, confidence
            case scoreVersion = "score_version"
            case recommendationCode = "recommendation_code"
            case morningHRV = "morning_hrv_rmssd_ms"
            case morningRestingHeartRate = "morning_resting_hr_bpm"
        }
    }

    struct Confidence: Decodable, Sendable {
        let score: Double?
        let level: String?
        let missingGroups: [String]

        enum CodingKeys: String, CodingKey {
            case score, level
            case missingGroups = "missing_groups"
        }
    }

    struct Sleep: Decodable, Sendable {
        let durationMinutes: MobileMetric
        let score: MobileMetric
        let nightlyHRV: MobileMetric
        let restingHeartRate: MobileMetric

        enum CodingKeys: String, CodingKey {
            case score
            case durationMinutes = "duration_minutes"
            case nightlyHRV = "nightly_hrv_rmssd_ms"
            case restingHeartRate = "resting_hr_bpm"
        }
    }

    struct Training: Decodable, Sendable {
        let sessionCount: Int
        let durationMinutes: Double?
        let caloriesKcal: Double?
        let sports: [String]

        enum CodingKeys: String, CodingKey {
            case sports
            case sessionCount = "session_count"
            case durationMinutes = "duration_minutes"
            case caloriesKcal = "calories_kcal"
        }
    }
}

struct MobileMetric: Decodable, Sendable {
    let value: Double?
    let provenance: Provenance

    struct Provenance: Decodable, Sendable {
        let value: Double?
        let source: String
        let isFallback: Bool
        let isManualOverride: Bool
        let reason: String

        enum CodingKeys: String, CodingKey {
            case value, source, reason
            case isFallback = "is_fallback"
            case isManualOverride = "is_manual_override"
        }
    }
}

extension MobileDailySnapshot {
    static let expectedKind = "rhythmos.mobile_daily_snapshot"
    static let supportedVersion = 1

    func asDailySnapshot() throws -> DailySnapshot {
        guard kind == Self.expectedKind, version == Self.supportedVersion else {
            throw MobileSnapshotError.unsupportedContract(kind: kind, version: version)
        }
        guard ([
            recovery.morningHRV,
            recovery.morningRestingHeartRate,
            sleep.durationMinutes,
            sleep.score,
            sleep.nightlyHRV,
            sleep.restingHeartRate,
        ].allSatisfy { $0.hasConsistentProvenance }) else {
            throw MobileSnapshotError.inconsistentMetricProvenance
        }
        let dateFormatter = ISO8601DateFormatter()
        dateFormatter.formatOptions = [.withFullDate]
        guard let day = dateFormatter.date(from: date) else {
            throw MobileSnapshotError.invalidDate(date)
        }

        let confidence = DataConfidence(rawValue: recovery.confidence?.level ?? "") ?? .building
        let hrv = recovery.morningHRV.value ?? sleep.nightlyHRV.value
        let restingHeartRate = recovery.morningRestingHeartRate.value ?? sleep.restingHeartRate.value
        return DailySnapshot(
            date: day,
            recovery: RecoverySummary(
                status: ReadinessStatus(rawValue: recovery.status) ?? .insufficientData,
                confidence: confidence,
                explanation: recoveryExplanation
            ),
            sleep: metric(
                id: "sleep",
                label: "睡眠",
                value: durationText(sleep.durationMinutes.value),
                detail: "睡眠时长",
                rawValue: sleep.durationMinutes.value
            ),
            hrv: metric(
                id: "hrv",
                label: "HRV",
                value: numberText(hrv, suffix: " ms"),
                detail: hrv == recovery.morningHRV.value ? "晨间 RMSSD" : "夜间 RMSSD",
                rawValue: hrv
            ),
            restingHeartRate: metric(
                id: "rhr",
                label: "静息心率",
                value: numberText(restingHeartRate, suffix: " bpm"),
                detail: "个人记录",
                rawValue: restingHeartRate
            ),
            nextAction: nextAction
        )
    }

    private var recoveryExplanation: String {
        guard let score = recovery.score else {
            return "继续记录晨间与睡眠数据，以建立个人基线。"
        }
        return "今日恢复分数为 \(Int(score.rounded()))。请结合数据完整度与身体感受安排训练。"
    }

    private var nextAction: String {
        switch recovery.recommendationCode {
        case "normal_training": return "按计划正常训练"
        case "moderate_training": return "将训练调整为适度负荷"
        case "reduced_training": return "减少今天的训练负荷"
        case "recovery_first": return "优先恢复与轻度活动"
        default: return "完成一次晨间恢复记录"
        }
    }

    private func metric(id: String, label: String, value: String, detail: String, rawValue: Double?) -> MetricValue {
        MetricValue(
            id: id,
            label: label,
            value: value,
            detail: rawValue == nil ? "尚未记录" : detail,
            state: rawValue == nil ? .unavailable : .neutral
        )
    }

    private func durationText(_ minutes: Double?) -> String {
        guard let minutes else { return "—" }
        let rounded = Int(minutes.rounded())
        return "\(rounded / 60) h \(rounded % 60) min"
    }

    private func numberText(_ value: Double?, suffix: String) -> String {
        guard let value else { return "—" }
        return "\(value.formatted(.number.precision(.fractionLength(0))))\(suffix)"
    }
}

enum MobileSnapshotError: LocalizedError {
    case unsupportedContract(kind: String, version: Int)
    case invalidDate(String)
    case inconsistentMetricProvenance

    var errorDescription: String? {
        switch self {
        case let .unsupportedContract(kind, version):
            return "Unsupported mobile snapshot: \(kind) v\(version)."
        case let .invalidDate(value):
            return "Invalid snapshot date: \(value)."
        case .inconsistentMetricProvenance:
            return "A measurement does not match its provenance value."
        }
    }
}

private extension MobileMetric {
    var hasConsistentProvenance: Bool {
        value == provenance.value
    }
}
