import SwiftUI
import UIKit

#if canImport(GoogleSignIn)
import GoogleSignIn
#endif

/// はじめの画面。Web版のウェルカムと同じ、ちゃむが迎えてくれる入口。
struct SignInView: View {
    @EnvironmentObject private var auth: AuthStore
    @State private var isWorking = false

    var body: some View {
        VStack(spacing: 0) {
            Spacer(minLength: 24)

            VStack(spacing: 18) {
                ChamuAvatar(size: 108)

                VStack(spacing: 6) {
                    Text("AI TRAVEL COMPANION")
                        .font(.kicker)
                        .tracking(4.2)
                        .foregroundStyle(Theme.Palette.kicker)
                    Text("たびメイト")
                        .font(Theme.Font_.rounded(34, weight: .bold))
                        .foregroundStyle(Theme.Palette.textMain)
                }

                Text("行きたい気持ちを話すだけで、\nちゃむが旅のしおりを作ります。")
                    .font(.body_)
                    .multilineTextAlignment(.center)
                    .lineSpacing(7)
                    .foregroundStyle(Theme.Palette.textMuted)
            }

            Spacer(minLength: 28)

            VStack(spacing: 14) {
                if let message = auth.errorMessage {
                    ErrorNote(message: message)
                        .padding(.horizontal, 8)
                        .padding(.bottom, 4)
                }

                Button {
                    Task { await signIn() }
                } label: {
                    HStack(spacing: 10) {
                        if isWorking {
                            ProgressView().tint(.white)
                        } else {
                            Image(systemName: "person.crop.circle")
                        }
                        Text(isWorking ? "サインインしています…" : "Googleではじめる")
                    }
                }
                .buttonStyle(CloverButtonStyle())
                .disabled(isWorking)

                Text("メールアドレスとお名前だけをお預かりします。")
                    .font(.meta)
                    .foregroundStyle(Theme.Palette.textMuted)
            }
            .padding(.horizontal, 28)
            .padding(.bottom, 44)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .paperBackground()
    }

    @MainActor
    private func signIn() async {
        #if canImport(GoogleSignIn)
        guard let root = UIApplication.shared.topViewController else { return }
        isWorking = true
        await auth.signIn(presenting: root)
        isWorking = false
        #else
        auth.errorMessage = "GoogleSignIn がまだ組み込まれていません（ios/README.md の手順を見てね）。"
        #endif
    }
}

extension UIApplication {
    /// いま前面にある画面。GoogleSignIn のシートを出すために要る。
    var topViewController: UIViewController? {
        let window = connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .flatMap(\.windows)
            .first { $0.isKeyWindow }
        var top = window?.rootViewController
        while let presented = top?.presentedViewController { top = presented }
        return top
    }
}
