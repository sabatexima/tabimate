// たびメイトの Service Worker（PWAインストール要件のための最小構成）。
// SSEストリーミング・OAuthリダイレクト・署名付き写真URLを壊さないよう、
// キャッシュ戦略は持たずすべてネットワークへ素通しする。
// （オフライン対応を足すときは、静的アセットに限定した cache-first をここに実装する）
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => { /* ネットワーク素通し */ });
