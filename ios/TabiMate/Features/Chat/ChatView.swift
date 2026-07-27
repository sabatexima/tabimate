import SwiftUI

/// ちゃむとの相談画面。話しかけると旅のしおりを組んでくれる。
struct ChatView: View {
    @StateObject private var model = ChatViewModel()
    @State private var showResetConfirm = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                transcript
                composer
            }
            .paperBackground()
            .navigationTitle("そうだん")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showResetConfirm = true } label: {
                        Image(systemName: "arrow.counterclockwise")
                    }
                    .accessibilityLabel("新しい相談をはじめる")
                    .disabled(model.messages.isEmpty || model.isGenerating)
                }
            }
            .confirmationDialog("この相談を消して、新しくはじめる？",
                                isPresented: $showResetConfirm, titleVisibility: .visible) {
                Button("新しくはじめる", role: .destructive) {
                    Task { await model.resetConversation() }
                }
                Button("やめる", role: .cancel) {}
            }
            .task { await model.load() }
        }
    }

    // MARK: - やりとり

    private var transcript: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 18) {
                    if model.isLoading {
                        LoadingClover().frame(maxWidth: .infinity)
                    } else if model.messages.isEmpty {
                        ChamuBubble(text: "どんな旅にしたい？\n行き先や日にち、予算のことも教えてね。")
                            .padding(.top, 8)
                    }

                    ForEach(model.messages) { message in
                        MessageRow(message: message) { plan in
                            await model.save(plan: plan)
                        }
                        .id(message.id)
                    }

                    if model.isGenerating {
                        ThinkingBubble().id(thinkingAnchor)
                    }

                    if let error = model.errorMessage {
                        ErrorNote(message: error).id(errorAnchor)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 18)
            }
            .onChange(of: model.messages.count) { scrollToEnd(proxy) }
            .onChange(of: model.isGenerating) { scrollToEnd(proxy) }
            .onChange(of: model.errorMessage) { scrollToEnd(proxy) }
        }
    }

    private var thinkingAnchor: String { "thinking" }
    private var errorAnchor: String { "error" }

    /// いちばん下（＝いま起きていること）が見えるところまで送る。
    private func scrollToEnd(_ proxy: ScrollViewProxy) {
        let target: AnyHashable?
        if model.errorMessage != nil {
            target = errorAnchor
        } else if model.isGenerating {
            target = thinkingAnchor
        } else {
            target = model.messages.last?.id
        }
        guard let target else { return }
        withAnimation(.easeOut(duration: 0.25)) {
            proxy.scrollTo(target, anchor: .bottom)
        }
    }

    // MARK: - 入力

    private var composer: some View {
        HStack(alignment: .bottom, spacing: 10) {
            TextField("行きたい場所や気分を書いてね", text: $model.draft, axis: .vertical)
                .font(.body_)
                .lineLimit(1...5)
                .padding(.horizontal, 15)
                .padding(.vertical, 11)
                .background(Theme.Palette.surface, in: RoundedRectangle(cornerRadius: 18))
                .overlay(
                    RoundedRectangle(cornerRadius: 18)
                        .stroke(Theme.Palette.borderInput, lineWidth: 1)
                )
                .disabled(model.isGenerating)

            if model.isGenerating {
                Button {
                    Task { await model.abort() }
                } label: {
                    Image(systemName: "stop.fill")
                        .foregroundStyle(.white)
                        .frame(width: 44, height: 44)
                        .background(Theme.Palette.danger, in: Circle())
                }
                .accessibilityLabel("生成をやめる")
            } else {
                Button {
                    Task { await model.send() }
                } label: {
                    Image(systemName: "paperplane.fill")
                        .foregroundStyle(.white)
                        .frame(width: 44, height: 44)
                        .background(canSend ? Theme.Palette.primary : Theme.Palette.border,
                                    in: Circle())
                }
                .disabled(!canSend)
                .accessibilityLabel("送る")
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(.ultraThinMaterial)
        .overlay(alignment: .top) {
            Rectangle().fill(Theme.Palette.border).frame(height: 1)
        }
    }

    private var canSend: Bool {
        !model.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
}

// MARK: - 1件ぶんの表示

private struct MessageRow: View {
    let message: ChatMessage
    let onSave: (DraftPlan) async -> Bool

    var body: some View {
        if message.isUser {
            HStack {
                Spacer(minLength: 44)
                Text(message.content)
                    .font(.body_)
                    .lineSpacing(5)
                    .foregroundStyle(.white)
                    .padding(.horizontal, 15)
                    .padding(.vertical, 11)
                    .background(Theme.Palette.primary, in: RoundedRectangle(cornerRadius: 16))
            }
        } else if let plan = message.plan {
            PlanProposalCard(plan: plan) { await onSave(plan) }
        } else {
            ChamuBubble(text: message.content.strippingHTML)
        }
    }
}

/// 「まだ考えてるよ」の吹き出し。四つ葉が順に灯る。
private struct ThinkingBubble: View {
    @State private var phase = 0

    var body: some View {
        HStack(alignment: .bottom, spacing: 10) {
            ChamuAvatar(size: 46)
            HStack(spacing: 5) {
                ForEach(0..<3, id: \.self) { index in
                    Text("🍀")
                        .font(.system(size: 13))
                        .opacity(phase == index ? 1 : 0.28)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 13)
            .background(Theme.Palette.surface, in: Capsule())
            .overlay(Capsule().stroke(Theme.Palette.border, lineWidth: 1))
            Text("旅のしおりを作っています…")
                .font(.meta)
                .foregroundStyle(Theme.Palette.textMuted)
        }
        .task {
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(420))
                phase = (phase + 1) % 3
            }
        }
    }
}

extension String {
    /// サーバーの会話文にまれに混ざるタグを落として、素の文章にする。
    var strippingHTML: String {
        replacingOccurrences(of: "<[^>]+>", with: "", options: .regularExpression)
            .replacingOccurrences(of: "&nbsp;", with: " ")
            .replacingOccurrences(of: "&amp;", with: "&")
            .replacingOccurrences(of: "&lt;", with: "<")
            .replacingOccurrences(of: "&gt;", with: ">")
            .replacingOccurrences(of: "&quot;", with: "\"")
            .replacingOccurrences(of: "&#39;", with: "'")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
