import SwiftUI

@main
struct RHYTHMOSApp: App {
    var body: some Scene {
        WindowGroup {
            AppView(repository: LocalDashboardRepository())
        }
    }
}
