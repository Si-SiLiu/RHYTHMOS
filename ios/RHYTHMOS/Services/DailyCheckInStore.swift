import Foundation

/// Persists only user-authored check-ins in the app sandbox. This store never
/// writes to the desktop database or changes an imported daily snapshot.
struct DailyCheckInStore: Sendable {
    private static let version = 1
    private let fileURL: URL
    private let calendar: Calendar

    init(fileURL: URL? = nil, calendar: Calendar = Calendar(identifier: .gregorian)) {
        self.fileURL = fileURL ?? Self.defaultFileURL()
        self.calendar = calendar
    }

    func load(on date: Date) throws -> DailyCheckIn? {
        try entries().first { calendar.isDate($0.date, inSameDayAs: date) }
    }

    func all() throws -> [DailyCheckIn] {
        try entries().sorted { $0.date > $1.date }
    }

    func save(_ checkIn: DailyCheckIn) throws {
        var savedEntries = try entries()
        savedEntries.removeAll { calendar.isDate($0.date, inSameDayAs: checkIn.date) }
        savedEntries.append(checkIn)
        try write(savedEntries)
    }

    func remove(on date: Date) throws {
        var savedEntries = try entries()
        savedEntries.removeAll { calendar.isDate($0.date, inSameDayAs: date) }
        try write(savedEntries)
    }

    private func entries() throws -> [DailyCheckIn] {
        guard FileManager.default.fileExists(atPath: fileURL.path) else { return [] }
        let archive = try JSONDecoder().decode(Archive.self, from: Data(contentsOf: fileURL))
        guard archive.version == Self.version else {
            throw DailyCheckInStoreError.unsupportedVersion(archive.version)
        }
        return archive.entries
    }

    private func write(_ entries: [DailyCheckIn]) throws {
        try FileManager.default.createDirectory(
            at: fileURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        let archive = Archive(version: Self.version, entries: entries.sorted { $0.date < $1.date })
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        try encoder.encode(archive).write(to: fileURL, options: .atomic)
    }

    private static func defaultFileURL() -> URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        return base
            .appendingPathComponent("RHYTHMOS", isDirectory: true)
            .appendingPathComponent("daily-check-ins-v1.json")
    }

    private struct Archive: Codable, Sendable {
        let version: Int
        let entries: [DailyCheckIn]
    }
}

enum DailyCheckInStoreError: LocalizedError {
    case unsupportedVersion(Int)

    var errorDescription: String? {
        switch self {
        case let .unsupportedVersion(version):
            return "无法读取此版本的本地记录（v\(version)）。"
        }
    }
}
