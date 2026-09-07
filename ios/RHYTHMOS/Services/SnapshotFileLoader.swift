import Foundation

enum SnapshotFileLoader {
    /// Decode a user-selected mobile projection without retaining the source file
    /// or granting the app ongoing access to its containing folder.
    static func load(from url: URL) throws -> ImportedSnapshot {
        let accessedSecurityScope = url.startAccessingSecurityScopedResource()
        defer {
            if accessedSecurityScope {
                url.stopAccessingSecurityScopedResource()
            }
        }
        let data = try Data(contentsOf: url)
        return ImportedSnapshot(
            snapshot: try JSONDecoder().decode(MobileDailySnapshot.self, from: data).asDailySnapshot(),
            rawData: data
        )
    }
}

struct ImportedSnapshot {
    let snapshot: DailySnapshot
    let rawData: Data
}
