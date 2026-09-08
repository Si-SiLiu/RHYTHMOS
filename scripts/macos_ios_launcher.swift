import Foundation

// This helper is packaged inside RHYTHMOS.app and opened directly from the
// desktop. It deliberately has no window and never invokes Terminal.
let projectRoot = URL(fileURLWithPath: "__PROJECT_ROOT__")
let launcher = projectRoot.appendingPathComponent("scripts/open_ios_simulator.command")

guard FileManager.default.isExecutableFile(atPath: launcher.path) else {
    exit(1)
}

let process = Process()
process.executableURL = URL(fileURLWithPath: "/usr/bin/nohup")
process.arguments = [launcher.path, "--background"]
process.currentDirectoryURL = projectRoot
process.standardInput = FileHandle.nullDevice
process.standardOutput = FileHandle.nullDevice
process.standardError = FileHandle.nullDevice

do {
    try process.run()
} catch {
    exit(1)
}
