import SwiftUI

struct RecoveryDetailView: View {
    let snapshot: DailySnapshot

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                RecoveryScoreCard(snapshot: snapshot)
                ConfidenceCard(details: snapshot.recoveryDetails)
                EvidenceSection(title: "晨间数据", metrics: [
                    snapshot.recoveryDetails.morningHRV,
                    snapshot.recoveryDetails.morningRestingHeartRate,
                ])
                RecommendationCard(text: snapshot.nextAction)
            }
            .padding(16)
        }
        .background(Color(uiColor: .systemGroupedBackground))
        .navigationTitle("恢复")
        .navigationBarTitleDisplayMode(.inline)
    }
}

struct SleepDetailView: View {
    let snapshot: DailySnapshot

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                SleepOverview(details: snapshot.sleepDetails)
                EvidenceSection(title: "昨夜睡眠", metrics: [
                    snapshot.sleepDetails.nightlyHRV,
                    snapshot.sleepDetails.restingHeartRate,
                    snapshot.sleepDetails.respirationRate,
                ])
                Text("睡眠数据仅展示已导入快照中的当日结果；缺失值会保留为未记录。")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 4)
            }
            .padding(16)
        }
        .background(Color(uiColor: .systemGroupedBackground))
        .navigationTitle("睡眠")
        .navigationBarTitleDisplayMode(.inline)
    }
}

private struct RecoveryScoreCard: View {
    let snapshot: DailySnapshot

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(snapshot.recovery.status.title, systemImage: snapshot.recovery.status.systemImage)
                .font(.headline)
                .foregroundStyle(statusColor)
            HStack(alignment: .lastTextBaseline, spacing: 8) {
                Text(scoreText)
                    .font(.system(size: 52, weight: .semibold, design: .rounded))
                    .monospacedDigit()
                if snapshot.recoveryDetails.score != nil {
                    Text("恢复分")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }
            Text(snapshot.recovery.explanation)
                .foregroundStyle(.secondary)
            if let version = snapshot.recoveryDetails.scoreVersion {
                Text("评分版本 \(version)")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(20)
        .background(.background, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    private var scoreText: String {
        guard let score = snapshot.recoveryDetails.score else { return "—" }
        return score.formatted(.number.precision(.fractionLength(0)))
    }

    private var statusColor: Color {
        switch snapshot.recovery.status {
        case .ready: return .green
        case .steady: return .rhythmosAccent
        case .conserve: return .orange
        case .insufficientData: return .secondary
        }
    }
}

private struct ConfidenceCard: View {
    let details: RecoveryDetails

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("数据可靠性")
                    .font(.headline)
                Spacer()
                Text(details.confidence.title)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(confidenceColor)
            }
            if let score = details.confidenceScore {
                Text("\(score.formatted(.number.precision(.fractionLength(0)))) / 100")
                    .font(.title3.monospacedDigit())
            }
            if details.missingGroups.isEmpty {
                Text("导入快照未报告缺失的数据组。")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                Text("待补充：\(details.missingGroups.map(localizedGroupName).joined(separator: "、"))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if let version = details.confidenceVersion {
                Text("置信度版本 \(version)")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(.background, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private var confidenceColor: Color {
        switch details.confidence {
        case .high: return .green
        case .medium: return .rhythmosAccent
        case .building, .low, .veryLow: return .orange
        }
    }
}

private struct SleepOverview: View {
    let details: SleepDetails

    var body: some View {
        HStack(spacing: 12) {
            SleepHeadlineMetric(metric: details.duration)
            SleepHeadlineMetric(metric: details.score)
        }
    }
}

private struct SleepHeadlineMetric: View {
    let metric: DetailMetric

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(metric.label)
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Text(metric.value)
                .font(.title2.monospacedDigit())
            SourceCaption(provenance: metric.provenance)
        }
        .frame(maxWidth: .infinity, minHeight: 126, alignment: .leading)
        .padding(16)
        .background(.background, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

private struct EvidenceSection: View {
    let title: String
    let metrics: [DetailMetric]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(title)
                .font(.headline)
                .padding(.bottom, 8)
            ForEach(metrics) { metric in
                HStack(alignment: .center, spacing: 12) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(metric.label)
                            .font(.subheadline)
                        SourceCaption(provenance: metric.provenance)
                    }
                    Spacer()
                    Text(metric.value)
                        .font(.body.monospacedDigit())
                        .foregroundStyle(metric.rawValue == nil ? .secondary : .primary)
                }
                .padding(.vertical, 12)
                if metric.id != metrics.last?.id {
                    Divider()
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(.background, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

private struct RecommendationCard: View {
    let text: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("今天的建议")
                .font(.headline)
            Text(text)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(.background, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

private struct SourceCaption: View {
    let provenance: MetricProvenance

    var body: some View {
        Text(sourceText)
            .font(.caption)
            .foregroundStyle(.secondary)
    }

    private var sourceText: String {
        var parts = [localizedSourceName(provenance.source)]
        if provenance.isFallback { parts.append("回退值") }
        if provenance.isManualOverride { parts.append("手动修订") }
        return parts.joined(separator: " · ")
    }
}

private func localizedSourceName(_ source: String) -> String {
    switch source.lowercased() {
    case "polar": return "Polar"
    case "kubios": return "Kubios"
    case "daily_metric": return "日汇总"
    case "missing": return "未记录"
    default: return source
    }
}

private func localizedGroupName(_ group: String) -> String {
    switch group.lowercased() {
    case "sleep": return "睡眠"
    case "hrv": return "HRV"
    case "respiration": return "呼吸率"
    case "readiness": return "恢复支持数据"
    default: return group
    }
}

#Preview {
    RecoveryDetailView(snapshot: try! MobileDailySnapshot(
        kind: "rhythmos.mobile_daily_snapshot",
        version: 1,
        generatedAt: "2026-09-07T00:00:00Z",
        date: "2026-09-07",
        recovery: .init(
            status: "ready", score: 84, scoreVersion: "1.0.0", recommendationCode: "normal_training",
            confidence: .init(score: 86, level: "high", missingGroups: [], version: "1.0.0"),
            morningHRV: .init(value: 44, provenance: .init(value: 44, source: "kubios", isFallback: false, isManualOverride: false, reason: "available")),
            morningRestingHeartRate: .init(value: 56, provenance: .init(value: 56, source: "kubios", isFallback: false, isManualOverride: false, reason: "available"))
        ),
        sleep: .init(
            durationMinutes: .init(value: 450, provenance: .init(value: 450, source: "polar", isFallback: false, isManualOverride: false, reason: "available")),
            score: .init(value: 82, provenance: .init(value: 82, source: "polar", isFallback: false, isManualOverride: false, reason: "available")),
            nightlyHRV: .init(value: 52, provenance: .init(value: 52, source: "polar", isFallback: false, isManualOverride: false, reason: "available")),
            restingHeartRate: .init(value: 49, provenance: .init(value: 49, source: "polar", isFallback: false, isManualOverride: false, reason: "available")),
            respirationRate: .init(value: 14, provenance: .init(value: 14, source: "polar", isFallback: false, isManualOverride: false, reason: "available"))
        ),
        training: .init(sessionCount: 0, durationMinutes: nil, caloriesKcal: nil, sports: [])
    ).asDailySnapshot())
}
