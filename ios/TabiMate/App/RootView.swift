import SwiftUI

/// 起動直後の分岐と、サインイン後のタブ。
struct RootView: View {
    @EnvironmentObject private var auth: AuthStore

    var body: some View {
        Group {
            if auth.isRestoring {
                LaunchView()
            } else if auth.isSignedIn {
                MainTabView()
            } else {
                SignInView()
            }
        }
        .animation(.easeInOut(duration: 0.25), value: auth.isSignedIn)
        .animation(.easeInOut(duration: 0.25), value: auth.isRestoring)
    }
}

/// 起動中。四つ葉だけを置いた静かな画面。
private struct LaunchView: View {
    var body: some View {
        VStack(spacing: 14) {
            ChamuAvatar(size: 84)
            Text("たびメイト")
                .font(Theme.Font_.rounded(19, weight: .bold))
                .foregroundStyle(Theme.Palette.textMain)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .paperBackground()
    }
}

/// 4つの入り口。ホーム・相談・保存プラン・おもいで。
struct MainTabView: View {
    @State private var selection = Tab.home

    enum Tab: Hashable { case home, chat, plans, memories }

    var body: some View {
        TabView(selection: $selection) {
            HomeView(startChat: { selection = .chat },
                     openPlans: { selection = .plans })
                .tabItem { Label("ホーム", systemImage: "house") }
                .tag(Tab.home)

            ChatView()
                .tabItem { Label("そうだん", systemImage: "bubble.left.and.bubble.right") }
                .tag(Tab.chat)

            PlanListView()
                .tabItem { Label("保存プラン", systemImage: "book.closed") }
                .tag(Tab.plans)

            TripListView()
                .tabItem { Label("おもいで", systemImage: "photo.on.rectangle.angled") }
                .tag(Tab.memories)
        }
    }
}
