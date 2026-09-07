import SwiftUI

struct AppView: View {
    let repository: any DashboardRepository

    var body: some View {
        TabView {
            TodayView(repository: repository)
                .tabItem { Label("今天", systemImage: "sun.max") }

            CheckInTrendView()
                .tabItem { Label("趋势", systemImage: "chart.line.uptrend.xyaxis") }

            CheckInView()
                .tabItem { Label("记录", systemImage: "plus.circle") }

            PlaceholderView(title: "我的", message: "个人目标与数据源设置将在后续阶段加入。", symbol: "person")
                .tabItem { Label("我的", systemImage: "person") }
        }
        .tint(.rhythmosAccent)
    }
}

private struct PlaceholderView: View {
    let title: String
    let message: String
    let symbol: String

    var body: some View {
        ContentUnavailableView(title, systemImage: symbol, description: Text(message))
    }
}

#Preview {
    AppView(repository: SampleDashboardRepository())
}
