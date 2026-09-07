import SwiftUI

struct CheckInView: View {
    private let store: DailyCheckInStore
    @State private var date = Date.now
    @State private var perceivedRecovery: PerceivedRecovery = .moderate
    @State private var trainingIntent: TrainingIntent = .light
    @State private var note = ""
    @State private var hasSavedCheckIn = false
    @State private var confirmationMessage: String?
    @State private var errorMessage: String?

    init(store: DailyCheckInStore = DailyCheckInStore()) {
        self.store = store
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    DatePicker("日期", selection: $date, displayedComponents: .date)
                        .onChange(of: date) { _, newDate in
                            loadCheckIn(for: newDate)
                        }
                } footer: {
                    Text("这是个人主观感受，不会覆盖导入的睡眠、HRV 或恢复分数。")
                }

                Section("晨间感受") {
                    Picker("主观恢复", selection: $perceivedRecovery) {
                        ForEach(PerceivedRecovery.allCases, id: \.self) { value in
                            Text(value.title).tag(value)
                        }
                    }
                    .pickerStyle(.segmented)
                }

                Section("今天的计划") {
                    Picker("训练意愿", selection: $trainingIntent) {
                        ForEach(TrainingIntent.allCases, id: \.self) { value in
                            Text(value.title).tag(value)
                        }
                    }
                    .pickerStyle(.segmented)
                }

                Section("备注（可选）") {
                    TextEditor(text: $note)
                        .frame(minHeight: 112)
                        .onChange(of: note) { _, value in
                            if value.count > 500 { note = String(value.prefix(500)) }
                        }
                    Text("\(note.count)/500")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section {
                    Button("保存今日记录", systemImage: "checkmark") {
                        saveCheckIn()
                    }
                    .frame(maxWidth: .infinity)

                    if hasSavedCheckIn {
                        Button("移除这条记录", systemImage: "trash", role: .destructive) {
                            removeCheckIn()
                        }
                        .frame(maxWidth: .infinity)
                    }
                }
            }
            .navigationTitle("记录")
            .onAppear { loadCheckIn(for: date) }
            .alert("已保存", isPresented: Binding(
                get: { confirmationMessage != nil },
                set: { if !$0 { confirmationMessage = nil } }
            )) {
                Button("好", role: .cancel) {}
            } message: {
                Text(confirmationMessage ?? "")
            }
            .alert("无法保存记录", isPresented: Binding(
                get: { errorMessage != nil },
                set: { if !$0 { errorMessage = nil } }
            )) {
                Button("好", role: .cancel) {}
            } message: {
                Text(errorMessage ?? "未知错误")
            }
        }
    }

    private func loadCheckIn(for day: Date) {
        do {
            guard let checkIn = try store.load(on: day) else {
                perceivedRecovery = .moderate
                trainingIntent = .light
                note = ""
                hasSavedCheckIn = false
                return
            }
            perceivedRecovery = checkIn.perceivedRecovery
            trainingIntent = checkIn.trainingIntent
            note = checkIn.note ?? ""
            hasSavedCheckIn = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func saveCheckIn() {
        do {
            try store.save(DailyCheckIn(
                date: date,
                perceivedRecovery: perceivedRecovery,
                trainingIntent: trainingIntent,
                note: note.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty,
                updatedAt: .now
            ))
            hasSavedCheckIn = true
            confirmationMessage = "这条记录仅保存在本机。"
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func removeCheckIn() {
        do {
            try store.remove(on: date)
            note = ""
            perceivedRecovery = .moderate
            trainingIntent = .light
            hasSavedCheckIn = false
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}

#Preview {
    CheckInView()
}
