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
            sleep: MetricValue(
                id: "sleep", label: "睡眠", value: "—", detail: "尚未连接数据源", state: .unavailable
            ),
            hrv: MetricValue(
                id: "hrv", label: "HRV", value: "—", detail: "尚未连接数据源", state: .unavailable
            ),
            restingHeartRate: MetricValue(
                id: "rhr", label: "静息心率", value: "—", detail: "尚未连接数据源", state: .unavailable
            ),
            nextAction: "完成一次晨间恢复记录"
        )
    }
}
