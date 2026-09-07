import XCTest
@testable import RHYTHMOS

final class DailySnapshotTests: XCTestCase {
    func testEveryReadinessStatusHasUserFacingTitleAndSymbol() {
        for status in ReadinessStatus.allCases {
            XCTAssertFalse(status.title.isEmpty)
            XCTAssertFalse(status.systemImage.isEmpty)
        }
    }

    func testSampleRepositoryPreservesInsufficientDataState() async throws {
        let snapshot = try await SampleDashboardRepository().today()

        XCTAssertEqual(snapshot.recovery.status, .insufficientData)
        XCTAssertEqual(snapshot.recovery.confidence, .building)
        XCTAssertEqual(snapshot.sleep.state, .unavailable)
    }

    func testV1FixtureDecodesIntoExpectedDailySnapshot() throws {
        let snapshot = try decodeFixture()

        let dateFormatter = ISO8601DateFormatter()
        dateFormatter.formatOptions = [.withFullDate]
        XCTAssertEqual(dateFormatter.string(from: snapshot.date), "2026-09-07")
        XCTAssertEqual(snapshot.recovery.status, .ready)
        XCTAssertEqual(snapshot.recovery.confidence, .high)
        XCTAssertEqual(snapshot.recoveryDetails.score, 84)
        XCTAssertEqual(snapshot.recoveryDetails.confidenceScore, 86)
        XCTAssertEqual(snapshot.recoveryDetails.missingGroups, [])
        XCTAssertEqual(snapshot.recoveryDetails.morningHRV.provenance.source, "kubios")
        XCTAssertEqual(snapshot.recovery.explanation, "今日恢复分数为 84。请结合数据完整度与身体感受安排训练。")
        XCTAssertEqual(snapshot.sleep.value, "7 h 30 min")
        XCTAssertEqual(snapshot.sleepDetails.score.value, "82 分")
        XCTAssertEqual(snapshot.sleepDetails.nightlyHRV.value, "52 ms")
        XCTAssertEqual(snapshot.sleepDetails.restingHeartRate.value, "49 bpm")
        XCTAssertEqual(snapshot.sleepDetails.respirationRate.value, "14 次/分")
        XCTAssertEqual(snapshot.sleepDetails.duration.provenance.source, "polar")
        XCTAssertEqual(snapshot.hrv.value, "44 ms")
        XCTAssertEqual(snapshot.hrv.detail, "晨间 RMSSD")
        XCTAssertEqual(snapshot.restingHeartRate.value, "56 bpm")
        XCTAssertEqual(snapshot.training.sessionCount, 1)
        XCTAssertEqual(snapshot.training.durationMinutes, 45)
        XCTAssertEqual(snapshot.training.caloriesKcal, 460)
        XCTAssertEqual(snapshot.training.sports, ["running"])
        XCTAssertEqual(snapshot.nextAction, "按计划正常训练")
    }

    func testUnsupportedVersionThrowsUnsupportedContractError() throws {
        let data = try fixtureData(replacing: ["version": 2])
        let contract = try JSONDecoder().decode(MobileDailySnapshot.self, from: data)

        XCTAssertThrowsError(try contract.asDailySnapshot()) { error in
            guard case let MobileSnapshotError.unsupportedContract(kind, version) = error else {
                return XCTFail("Expected unsupported contract error, got \(error)")
            }
            XCTAssertEqual(kind, MobileDailySnapshot.expectedKind)
            XCTAssertEqual(version, 2)
        }
    }

    func testUnsupportedKindThrowsUnsupportedContractError() throws {
        let data = try fixtureData(replacing: ["kind": "rhythmos.unsupported_snapshot"])
        let contract = try JSONDecoder().decode(MobileDailySnapshot.self, from: data)

        XCTAssertThrowsError(try contract.asDailySnapshot()) { error in
            guard case let MobileSnapshotError.unsupportedContract(kind, version) = error else {
                return XCTFail("Expected unsupported contract error, got \(error)")
            }
            XCTAssertEqual(kind, "rhythmos.unsupported_snapshot")
            XCTAssertEqual(version, 1)
        }
    }

    func testApprovedSnapshotPersistsOnlyInAppSandbox() throws {
        try SnapshotStore.remove()
        defer { try? SnapshotStore.remove() }
        let fixture = try fixtureData()

        try SnapshotStore.save(fixture)

        XCTAssertTrue(SnapshotStore.hasSavedSnapshot())
        XCTAssertEqual(try SnapshotStore.load(), fixture)
    }

    func testDailyCheckInStoreKeepsOneEntryPerDayAndPreservesOtherDays() throws {
        let fileURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
            .appendingPathComponent("check-ins.json")
        defer { try? FileManager.default.removeItem(at: fileURL.deletingLastPathComponent()) }
        let store = DailyCheckInStore(fileURL: fileURL)
        let calendar = Calendar(identifier: .gregorian)
        let today = calendar.startOfDay(for: .now)
        let yesterday = calendar.date(byAdding: .day, value: -1, to: today)!

        let prior = DailyCheckIn(
            date: yesterday, perceivedRecovery: .low, trainingIntent: .rest, note: "休息", updatedAt: .now
        )
        let latest = DailyCheckIn(
            date: today, perceivedRecovery: .good, trainingIntent: .normal, note: nil, updatedAt: .now
        )
        try store.save(prior)
        try store.save(latest)

        XCTAssertEqual(try store.load(on: today), latest)
        XCTAssertEqual(try store.all().map(\.date), [today, yesterday])

        try store.remove(on: today)
        XCTAssertNil(try store.load(on: today))
        XCTAssertEqual(try store.load(on: yesterday), prior)
    }

    private func decodeFixture() throws -> DailySnapshot {
        let contract = try JSONDecoder().decode(MobileDailySnapshot.self, from: fixtureData())
        return try contract.asDailySnapshot()
    }

    private func fixtureData(replacing replacements: [String: Any] = [:]) throws -> Data {
        let fixtureURL = try XCTUnwrap(
            Bundle.main.url(forResource: "MobileDailySnapshot-v1", withExtension: "json"),
            "The app target must bundle the mobile snapshot fixture."
        )
        let originalData = try Data(contentsOf: fixtureURL)
        guard !replacements.isEmpty else { return originalData }

        var payload = try XCTUnwrap(
            try JSONSerialization.jsonObject(with: originalData) as? [String: Any]
        )
        replacements.forEach { payload[$0.key] = $0.value }
        return try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    }
}
