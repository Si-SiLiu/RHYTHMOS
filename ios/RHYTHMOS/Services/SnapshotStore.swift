import Foundation

enum SnapshotStore {
    private static let filename = "mobile-daily-snapshot.json"

    static func load() throws -> Data? {
        let url = try storageURL()
        guard FileManager.default.fileExists(atPath: url.path) else { return nil }
        return try Data(contentsOf: url)
    }

    static func save(_ data: Data) throws {
        // Validate first so a malformed file never replaces a valid local copy.
        _ = try JSONDecoder().decode(MobileDailySnapshot.self, from: data).asDailySnapshot()
        let url = try storageURL(createDirectory: true)
        try data.write(to: url, options: .atomic)
    }

    static func remove() throws {
        let url = try storageURL()
        guard FileManager.default.fileExists(atPath: url.path) else { return }
        try FileManager.default.removeItem(at: url)
    }

    static func hasSavedSnapshot() -> Bool {
        guard let url = try? storageURL() else { return false }
        return FileManager.default.fileExists(atPath: url.path)
    }

    private static func storageURL(createDirectory: Bool = false) throws -> URL {
        let root = try FileManager.default.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: createDirectory
        )
        let directory = root.appendingPathComponent("RHYTHMOS", isDirectory: true)
        if createDirectory {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        }
        return directory.appendingPathComponent(filename, isDirectory: false)
    }
}
