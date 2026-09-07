import Foundation

protocol DashboardRepository: Sendable {
    func today() async throws -> DailySnapshot
}

struct BundledDashboardRepository: DashboardRepository {
    func today() async throws -> DailySnapshot {
        guard let url = Bundle.main.url(
            forResource: "MobileDailySnapshot-v1",
            withExtension: "json"
        ) else {
            return try await SampleDashboardRepository().today()
        }
        let data = try Data(contentsOf: url)
        return try JSONDecoder().decode(MobileDailySnapshot.self, from: data).asDailySnapshot()
    }
}

struct LocalDashboardRepository: DashboardRepository {
    func today() async throws -> DailySnapshot {
        if let data = try SnapshotStore.load() {
            return try JSONDecoder().decode(MobileDailySnapshot.self, from: data).asDailySnapshot()
        }
        return try await BundledDashboardRepository().today()
    }
}

/// Preview-safe fallback when a bundled contract fixture is unavailable.
struct SampleDashboardRepository: DashboardRepository {
    func today() async throws -> DailySnapshot {
        DailySnapshot(
            date: .now,
            recovery: RecoverySummary(
                status: .insufficientData,
                confidence: .building,
                explanation: "继续记录晨间与睡眠数据，以建立个人基线。"
            ),
            recoveryDetails: RecoveryDetails(
                score: nil,
                scoreVersion: nil,
                confidenceScore: nil,
                confidence: .building,
                confidenceVersion: nil,
                missingGroups: ["晨间数据", "睡眠数据"],
                morningHRV: unavailableMetric(id: "morning-hrv", label: "晨间 HRV"),
                morningRestingHeartRate: unavailableMetric(id: "morning-rhr", label: "晨间静息心率")
            ),
            sleep: MetricValue(
                id: "sleep", label: "睡眠", value: "—", detail: "尚未连接数据源", state: .unavailable
            ),
            sleepDetails: SleepDetails(
                duration: unavailableMetric(id: "sleep-duration", label: "睡眠时长"),
                score: unavailableMetric(id: "sleep-score", label: "睡眠评分"),
                nightlyHRV: unavailableMetric(id: "nightly-hrv", label: "夜间 HRV"),
                restingHeartRate: unavailableMetric(id: "sleep-rhr", label: "夜间静息心率"),
                respirationRate: unavailableMetric(id: "respiration-rate", label: "呼吸率")
            ),
            hrv: MetricValue(
                id: "hrv", label: "HRV", value: "—", detail: "尚未连接数据源", state: .unavailable
            ),
            restingHeartRate: MetricValue(
                id: "rhr", label: "静息心率", value: "—", detail: "尚未连接数据源", state: .unavailable
            ),
            training: TrainingSummary(
                sessionCount: 0, durationMinutes: nil, caloriesKcal: nil, sports: []
            ),
            nextAction: "完成一次晨间恢复记录"
        )
    }

    private func unavailableMetric(id: String, label: String) -> DetailMetric {
        DetailMetric(
            id: id,
            label: label,
            value: "—",
            rawValue: nil,
            provenance: MetricProvenance(
                source: "missing",
                isFallback: false,
                isManualOverride: false,
                reason: "no_permitted_source_value_available"
            )
        )
    }
}
