# たびメイト iOS 🍀

Web版と同じサーバー・同じアカウント・同じしおりを、ネイティブアプリで。
SwiftUI で書かれていて、Web版のデザイン言語（クリームの紙・四つ葉の緑・付箋・ちゃむ）
をそのまま持ってきています。

> **ちゃむ**「ブラウザを開かなくても、ホーム画面からすぐ相談できるようになったよ！」

---

## できること

| | |
|---|---|
| 🔑 **Googleサインイン** | Web版と同じアカウント。しおりは共通 |
| 💬 **そうだん** | 話しかけるとプランを生成。途中でやめられる |
| 🔄 **中断からの復帰** | 生成中にアプリを閉じても、開き直せば続きが見える |
| 📖 **保存プラン** | 付箋を並べたボード。開くとしおりの中身 |
| 🗺 **地図** | 移動する順に番号を振ったピンを、その順で線でつなぐ |
| 🎒 **持ち物リスト** | ちゃむが旅の内容から考える。チェックは端末に残る |
| 💰 **おこづかい帳** | 見つもりと実際の差を並べて見る |

まだ入っていないもの: 旅の振り返り（写真・ベストショット）、共有、年間ダイジェスト。
Web版で引き続き使えます。

---

## 必要なもの

- macOS + **Xcode 15.3 以降**（iOS 17 以上を対象にしています）
- Apple ID（実機で動かすなら）
- Google Cloud コンソールへのアクセス（iOS 用クライアントIDを作るため）

---

## 準備

### 1. Google の iOS クライアントIDを作る

1. [Google Cloud コンソール](https://console.cloud.google.com/apis/credentials) →
   「認証情報を作成」→「OAuth クライアントID」→ **iOS**
2. バンドルID に `app.tabimate.ios` を入れる（変えるなら後の設定も合わせる）
3. できた **クライアントID** と **iOS URL スキーム**（クライアントIDを逆順にしたもの）を控える

### 2. サーバー側の環境変数

Cloud Run（またはローカルの `.env`）に足します。

| 変数 | 例 | 説明 |
|---|---|---|
| `GOOGLE_IOS_CLIENT_ID` | `0000-xxxx.apps.googleusercontent.com` | アプリから来たIDトークンの検証先。未設定なら `GOOGLE_CLIENT_ID` が使われます |
| `APP_TOKEN_MAX_AGE_SEC` | `2592000` | アプリ用トークンの有効期間（既定30日） |

`SECRET_KEY` はWeb版と同じものを使います。**これを変えると発行済みのトークンは
すべて無効になり、アプリは再サインインを求めます**（意図的にそうしています）。

### 3. `ios/Config.xcconfig` を書き換える

```
TABIMATE_BASE_URL     = https:/$()/あなたのサーバー
GOOGLE_IOS_CLIENT_ID  = 上で作ったクライアントID
GOOGLE_IOS_URL_SCHEME = 上のURLスキーム
```

> `//` は xcconfig ではコメント開始なので、URL のスラッシュ2つは `$()` をはさんで
> `https:/$()/…` と書きます。Xcode の作法で、たびメイト固有の話ではありません。

---

## ビルド

### XcodeGen を使う場合（おすすめ）

```bash
brew install xcodegen
cd ios
xcodegen generate
open TabiMate.xcodeproj
```

あとは Xcode で ▶︎ を押すだけ。GoogleSignIn は SPM で自動的に取ってきます。

### 手で作る場合

1. Xcode →「Create New Project」→ **App**（Interface: SwiftUI、Language: Swift）
   - Product Name: `TabiMate` / Bundle Identifier: `app.tabimate.ios`
2. 生成されたテンプレートの `ContentView.swift` と `〜App.swift` を消す
3. `ios/TabiMate/` の中身をまるごとプロジェクトにドラッグ（"Create groups" を選ぶ）
4. File → Add Package Dependencies → `https://github.com/google/GoogleSignIn-iOS` を追加
5. Info.plist に次を足す
   - `TabiMateBaseURL`（String）… サーバーのURL
   - `GIDClientID`（String）… iOS クライアントID
   - `CFBundleURLTypes` → `CFBundleURLSchemes` に iOS URL スキーム
6. Deployment Target を **iOS 17.0** にする

---

## ローカルのサーバーにつなぐ

シミュレータからなら `http://localhost:8080` でそのまま届きます。
実機からは Mac の IP（`ipconfig getifaddr en0`）を使ってください。

`http://` は既定では通信がブロックされるので、開発中だけ Info.plist に
次を足します（**本番では消すこと**）。

```xml
<key>NSAppTransportSecurity</key>
<dict><key>NSAllowsLocalNetworking</key><true/></dict>
```

---

## フォントについて

Web版は **Zen Maru Gothic** を使っています。同じ字面にしたい場合:

1. [Google Fonts](https://fonts.google.com/specimen/Zen+Maru+Gothic) から
   `ZenMaruGothic-Regular.ttf` と `ZenMaruGothic-Bold.ttf` を落とす
2. `ios/TabiMate/Resources/` に置いてプロジェクトに追加
3. Info.plist の `UIAppFonts` に2つのファイル名を並べる

入れなくてもビルドは通ります。その場合は端末標準の丸ゴシック（SF Rounded）に
自動で落ちるようにしてあります（`Theme.Font_`）。

ちゃむの絵を出したい場合は、Assets に `chamu` という名前で画像を足してください。
無いときは 🍀 で代用します。

---

## 中身の地図

```
ios/TabiMate/
├── App/            起動と画面の分岐（サインイン済みかどうか）
├── Design/         Theme（色・書体・付箋）と共通部品
├── Networking/     APIClient / AuthStore / Keychain / 各サービス
└── Features/
    ├── SignIn/     はじめの画面
    ├── Home/       ちゃむのあいさつ、カウントダウン、季節のアイデア
    ├── Chat/       そうだん（SSE・中断・復帰・プランカード）
    ├── Plans/      保存プランのボード
    ├── PlanDetail/ しおりの中身、地図、持ち物、おこづかい帳
    └── Settings/   アカウントとサインアウト
```

### 認証のしくみ

```
iOS ──Googleサインイン──▶ IDトークン
    ──POST /auth/app/signin──▶ サーバーが検証してアプリ用トークンを発行
    ◀────────────────────── トークン（署名付き・30日）
    ──Authorization: Bearer …──▶ 以降のAPIすべて
```

トークンは Keychain に置きます。401 が返ったら自動的に捨てて、サインイン画面へ戻ります。

サーバー側は `login_required` がセッションCookieと Bearer の両方を受け付けます
（`src/api_auth.py` / `src/views/auth.py`）。Web版の動きは変えていません。
