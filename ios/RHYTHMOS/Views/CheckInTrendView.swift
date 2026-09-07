import Charts
import SwiftUI

/// Shows subjective trends only. Objective health trends require a separately
/// versioned history contract and are not inferred from manual entries.
struct CheckInTrendView: View {
    private let store: DailyCheckInStore
    @State private var entries: [DailyCheckIn] = []
    @State private var errorMessage: String?

    init(store: DailyCheckInStore = DailyCheckInStore()) {
        self.store = store
    }

    var body: some View {
        NavigationStack {
            Group {
                if entries.isEmpty {
                    ContentUnavailableView(
                        "还没有主观恢复记录",
                        systemImage: "chart.line.uptrend.xyaxis",
                        description: Text("前往“记录”页完成晨间感受后，这里会展示你的本地趋势。")
                    )
                } else {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 24) {
                            TrendChart(entries: Array(entries.prefix(14).reversed()))
                            CheckInHistory(entries: entries)
                        }
                        .padding(16)
                    }
                }
            }
            .background(Color(uiColor: .systemGroupedBackground))
            .navigationTitle("趋势")
            .onAppear(perform: loadEntries)
            .alert("无法读取记录", isPresented: Binding(
                get: { errorMessage != nil },
                set: { if !$0 { errorMessage = nil } }
            )) {
                Button("好", role: .cancel) {}
            } message: {
                Text(errorMessage ?? "未知错误")
            }
        }
    }

    private func loadEntries() {
        do {
            entries = try store.all()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

private struct TrendChart: View {
    let entries: [DailyCheckIn]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("主观恢复")
                .font(.headline)
            Text("最近 \(entries.count) 天的晨间自评")
                .font(.caption)
                .foregroundStyle(.secondary)

            Chart(entries) { entry in
                LineMark(
                    x: .value("日期", entry.date, unit: .day),
                    y: .value("主观恢复", entry.perceivedRecovery.score)
                )
                .foregroundStyle(Color.rhythmosAccent)
                .interpolationMethod(.catmullRom)

                PointMark(
                    x: .value("日期", entry.date, unit: .day),
                    y: .value("主观恢复", entry.perceivedRecovery.score)
                )
                .foregroundStyle(Color.rhythmosAccent)
            }
            .chartYScale(domain: 1...3)
            .chartYAxis {
                AxisMarks(values: [1, 2, 3]) { value in
                    AxisGridLine()
                    AxisValueLabel {
                        if let score = value.as(Int.self) {
                            Text(recoveryLabel(for: score))
                        }
                    }
                }
            }
            .frame(height: 210)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(.background, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private func recoveryLabel(for score: Int) -> String {
        switch score {
        case 1: return "偏低"
        case 2: return "一般"
        case 3: return "良好"
        default: return ""
        }
    }
}

private struct CheckInHistory: View {
    let entries: [DailyCheckIn]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("历史记录")
                .font(.headline)
            ForEach(entries) { entry in
                HStack {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(entry.date, format: .dateTime.month().day().weekday(.abbreviated))
                            .font(.subheadline.weight(.medium))
                        Text("主观恢复：\(entry.perceivedRecovery.title) · 计划：\(entry.trainingIntent.title)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Image(systemName: entry.perceivedRecovery == .good ? "arrow.up.right" : "minus")
                        .foregroundStyle(entry.perceivedRecovery == .low ? .orange : .rhythmosAccent)
                }
                .padding(.vertical, 8)

                if entry.id != entries.last?.id {
                    Divider()
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(.background, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

#Preview {
    CheckInTrendView()
}
