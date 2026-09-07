import SwiftUI
import UniformTypeIdentifiers

struct TodayView: View {
    let repository: any DashboardRepository
    @State private var snapshot: DailySnapshot?
    @State private var loadError: Error?
    @State private var showsSnapshotImporter = false
    @State private var snapshotSource = "本机演示快照"
    @State private var importErrorMessage: String?

    var body: some View {
        NavigationStack {
            Group {
                if let snapshot {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 24) {
                            RecoveryHero(summary: snapshot.recovery)
                            MetricGrid(metrics: [snapshot.sleep, snapshot.hrv, snapshot.restingHeartRate])
                            NextAction(text: snapshot.nextAction)
                            Text(snapshotSource)
                                .font(.caption)
                                .foregroundStyle(.tertiary)
                        }
                        .padding(16)
                    }
                } else if loadError != nil {
                    ContentUnavailableView("暂时无法读取今天的数据", systemImage: "exclamationmark.triangle", description: Text("请稍后重试。"))
                } else {
                    ProgressView()
                }
            }
            .background(Color(uiColor: .systemGroupedBackground))
            .navigationTitle("RHYTHMOS")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button("导入快照", systemImage: "square.and.arrow.down") {
                            showsSnapshotImporter = true
                        }
                        if SnapshotStore.hasSavedSnapshot() {
                            Button("移除本地快照", systemImage: "trash", role: .destructive) {
                                removeSavedSnapshot()
                            }
                        }
                    } label: {
                        Label("快照", systemImage: "square.and.arrow.down")
                    }
                    .accessibilityHint("选择由 RHYTHMOS 桌面端导出的每日快照 JSON 文件")
                }
            }
            .task { await loadToday() }
            .fileImporter(
                isPresented: $showsSnapshotImporter,
                allowedContentTypes: [.json],
                allowsMultipleSelection: false
            ) { result in
                importSnapshot(result)
            }
            .alert(
                "无法导入快照",
                isPresented: Binding(
                    get: { importErrorMessage != nil },
                    set: { if !$0 { importErrorMessage = nil } }
                )
            ) {
                Button("好", role: .cancel) {}
            } message: {
                Text(importErrorMessage ?? "文件无法读取。")
            }
        }
    }

    private func loadToday() async {
        do {
            snapshot = try await repository.today()
            snapshotSource = SnapshotStore.hasSavedSnapshot() ? "已保存的本地快照" : "本机演示快照"
        } catch {
            loadError = error
        }
    }

    private func importSnapshot(_ result: Result<[URL], Error>) {
        do {
            guard let url = try result.get().first else { return }
            let imported = try SnapshotFileLoader.load(from: url)
            try SnapshotStore.save(imported.rawData)
            snapshot = imported.snapshot
            snapshotSource = "已保存的本地快照"
            loadError = nil
        } catch {
            importErrorMessage = error.localizedDescription
        }
    }

    private func removeSavedSnapshot() {
        do {
            try SnapshotStore.remove()
            snapshotSource = "本机演示快照"
            Task { await loadToday() }
        } catch {
            importErrorMessage = error.localizedDescription
        }
    }
}

private struct RecoveryHero: View {
    let summary: RecoverySummary

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(summary.status.title, systemImage: summary.status.systemImage)
                .font(.headline)
                .foregroundStyle(statusColor)
            Text(summary.explanation)
                .font(.body)
                .foregroundStyle(.secondary)
            Text(summary.confidence.title)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(20)
        .background(.background, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(.quaternary, lineWidth: 1)
        }
    }

    private var statusColor: Color {
        switch summary.status {
        case .ready: return .green
        case .steady: return .rhythmosAccent
        case .conserve: return .orange
        case .insufficientData: return .secondary
        }
    }
}

private struct MetricGrid: View {
    let metrics: [MetricValue]
    private let columns = [GridItem(.flexible()), GridItem(.flexible())]

    var body: some View {
        LazyVGrid(columns: columns, alignment: .leading, spacing: 12) {
            ForEach(metrics) { metric in
                VStack(alignment: .leading, spacing: 6) {
                    Text(metric.label).font(.subheadline).foregroundStyle(.secondary)
                    Text(metric.value).font(.title2.monospacedDigit())
                    Text(metric.detail).font(.caption).foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, minHeight: 94, alignment: .leading)
                .padding(16)
                .background(.background, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            }
        }
    }
}

private struct NextAction: View {
    let text: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("下一步").font(.headline)
            Text(text).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
    }
}

#Preview {
    TodayView(repository: SampleDashboardRepository())
}
