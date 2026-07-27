import SwiftUI

/// 設定。今はアカウントとサインアウトだけ。
struct SettingsView: View {
    @EnvironmentObject private var auth: AuthStore
    @Environment(\.dismiss) private var dismiss
    @State private var showSignOutConfirm = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    if let user = auth.user {
                        Card {
                            VStack(alignment: .leading, spacing: 6) {
                                Text("サインイン中")
                                    .font(.meta)
                                    .foregroundStyle(Theme.Palette.textMuted)
                                Text(user.name)
                                    .font(.cardTitle)
                                    .foregroundStyle(Theme.Palette.textMain)
                                Text(user.email)
                                    .font(.meta)
                                    .foregroundStyle(Theme.Palette.textMuted)
                            }
                        }
                    }

                    Card {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("たびメイトについて")
                                .font(.cardTitle)
                                .foregroundStyle(Theme.Palette.textMain)
                            Text("行きたい気持ちを話すだけで、ちゃむが旅のしおりを作ります。\nWeb版と同じアカウントで、しおりは共通です。")
                                .font(.body_)
                                .lineSpacing(5)
                                .foregroundStyle(Theme.Palette.textMuted)
                            if let version = Bundle.main
                                .object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String {
                                Text("バージョン \(version)")
                                    .font(.meta)
                                    .foregroundStyle(Theme.Palette.textMuted)
                            }
                        }
                    }

                    Button("サインアウト") { showSignOutConfirm = true }
                        .buttonStyle(QuietButtonStyle(tint: Theme.Palette.danger))
                        .frame(maxWidth: .infinity)
                }
                .padding(20)
            }
            .paperBackground()
            .navigationTitle("設定")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("閉じる") { dismiss() }
                }
            }
            .confirmationDialog("サインアウトする？", isPresented: $showSignOutConfirm,
                                titleVisibility: .visible) {
                Button("サインアウト", role: .destructive) {
                    auth.signOut()
                    dismiss()
                }
                Button("やめる", role: .cancel) {}
            } message: {
                Text("しおりは消えません。またサインインすれば戻ってきます。")
            }
        }
    }
}
