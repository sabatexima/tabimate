import SwiftUI

#if canImport(GoogleSignIn)
import GoogleSignIn
#endif

@main
struct TabiMateApp: App {
    @StateObject private var auth = AuthStore.shared

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(auth)
                .tint(Theme.Palette.primary)
                .task { await auth.restoreSession() }
                .onOpenURL { url in
                    // Googleのサインインから戻ってきたときの受け口
                    #if canImport(GoogleSignIn)
                    GIDSignIn.sharedInstance.handle(url)
                    #endif
                }
        }
    }
}
