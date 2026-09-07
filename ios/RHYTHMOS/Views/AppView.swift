import SwiftUI

struct AppView: View {
    let repository: any DashboardRepository

    var body: some View {
        TabView {
            TodayView(repository: repository)
                .tabItem { Label("今天", systemImage: "sun.max") }

            PlaceholderView(title: "趋势", message: "历史趋势将在本地数据契约落地后提供。", symbol: "chart.xyaxis.line")
                .tabItem { Label("趋势", systemImage: "chart.line.uptrend.xyaxis") }

            PlaceholderView(title: "记录", message: "晨间、训练与营养记录正在准备中。", symbol: "square.and.pencil")
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
