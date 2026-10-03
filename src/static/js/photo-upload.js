/* 写真を1枚ずつ送り、進み具合を見せる（思い出の旅のページと、共有された旅のページで共用）。

   ■ なぜ1枚ずつか
     以前は選んだ写真を1回のリクエストにまとめて送っていた。本番の Cloud Run は
     1リクエスト32MBまでしか受け取らないので、スマホの写真（1枚3〜6MB）だと
     8枚ほどで超え、アプリに届く前に 413 で断られていた。
     1枚ずつなら上限は「1枚32MB」になり、途中の1枚が失敗しても残りは入る。

   ■ 写真は撮ったままのデータで送る
     縮めて作り直すと EXIF（撮影日時・場所）が落ち、タイムラインと地図が使えなくなる。

   ■ 進み具合
     送ったバイト数で棒を進め、「3 / 8 枚」を出す。入った写真から順に並べる。
     送っている間に閉じようとしたら、ブラウザの確認を出す。 */

(function () {
  // Cloud Run の上限（32MiB）から、multipart の包みのぶんを少し引いた値
  const MAX_BYTES = 31.5 * 1024 * 1024;

  // 1枚を送る。fetch では送信の進み具合が取れないので XMLHttpRequest を使う
  function sendOne(url, file, onBytes) {
    return new Promise((resolve) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', url);
      xhr.upload.onprogress = (e) => { if (e.lengthComputable) onBytes(e.loaded); };
      xhr.onload = () => {
        let data = null;
        try { data = JSON.parse(xhr.responseText); } catch (e) { /* HTML のエラーページなど */ }
        if (xhr.status >= 200 && xhr.status < 300 && data && Array.isArray(data.saved)) {
          resolve({ ok: true, saved: data.saved });
        } else if (xhr.status === 413) {
          resolve({ ok: false, reason: '大きすぎて送れませんでした' });
        } else {
          resolve({ ok: false, reason: (data && data.error) || '送れませんでした' });
        }
      };
      xhr.onerror = () => resolve({ ok: false, reason: '通信が切れました' });
      xhr.ontimeout = () => resolve({ ok: false, reason: '時間がかかりすぎました' });
      const fd = new FormData();
      fd.append('photos', file);
      xhr.send(fd);
    });
  }

  /* files を1枚ずつ（同時に concurrency 枚まで）送る。
     onSaved(写真)   入った写真から順に呼ぶ（画面に並べる）
     onProgress({done, total, ratio})  進み具合（ratio は送ったバイトの割合 0〜1）
     返り値: { saved: 入った枚数, failed: [{name, reason}] } */
  async function uploadPhotos({ files, url, onSaved, onProgress, concurrency = 2 }) {
    const list = Array.from(files || []);
    const totalBytes = list.reduce((s, f) => s + (f.size || 0), 0) || 1;
    const sentBytes = new Array(list.length).fill(0);
    const failed = [];
    let saved = 0;
    let done = 0;
    let next = 0;

    const report = () => {
      const ratio = Math.min(1, sentBytes.reduce((s, b) => s + b, 0) / totalBytes);
      if (onProgress) onProgress({ done, total: list.length, ratio });
    };
    report();

    async function worker() {
      while (next < list.length) {
        const i = next++;
        const file = list[i];
        let result;
        if ((file.size || 0) > MAX_BYTES) {
          result = { ok: false, reason: '1枚32MBを超えるため送れません' };
        } else {
          result = await sendOne(url, file, (loaded) => { sentBytes[i] = loaded; report(); });
        }
        sentBytes[i] = file.size || 0;   // 失敗しても「処理は済んだ」ぶんとして棒を進める
        done += 1;
        if (result.ok) {
          result.saved.forEach((p) => { saved += 1; if (onSaved) onSaved(p); });
        } else {
          failed.push({ name: file.name || `${i + 1}枚目`, reason: result.reason });
        }
        report();
      }
    }

    const leaveGuard = (e) => { e.preventDefault(); e.returnValue = ''; };
    window.addEventListener('beforeunload', leaveGuard);
    try {
      await Promise.all(Array.from({ length: Math.min(concurrency, list.length) }, worker));
    } finally {
      window.removeEventListener('beforeunload', leaveGuard);
    }
    return { saved, failed };
  }

  /* ページのボタン・選択欄・進み具合の表示をつなぐ（2つのページで同じ形）。
     url: 送り先、onSaved: 入った写真を並べる関数 */
  function wireUploader({ url, onSaved, onFinished }) {
    const input = document.getElementById('photo-input');
    const button = document.getElementById('upload-btn');
    const box = document.getElementById('upload-progress');
    const fill = document.getElementById('upload-bar-fill');
    const status = document.getElementById('upload-status');
    if (!input || !button) return;

    button.addEventListener('click', async () => {
      if (!input.files.length) { alert('写真を選択してください'); return; }
      const files = Array.from(input.files);
      button.disabled = true;
      input.disabled = true;
      button.textContent = 'アップロード中...';
      if (box) box.hidden = false;
      const show = ({ done, total, ratio }) => {
        if (fill) fill.style.width = `${Math.round(ratio * 100)}%`;
        if (status) status.textContent = `${done} / ${total} 枚`;
      };
      const result = await uploadPhotos({ files, url, onSaved, onProgress: show });
      input.value = '';
      const chosen = document.getElementById('photo-chosen');
      if (chosen) chosen.textContent = '';
      button.disabled = false;
      input.disabled = false;
      button.textContent = 'アップロード';
      if (result.failed.length) {
        if (status) status.textContent = `${result.saved}枚入りました・${result.failed.length}枚は入りませんでした`;
        alert(`${result.failed.length}枚の写真を入れられませんでした。\n`
              + result.failed.slice(0, 5).map((f) => `・${f.name}（${f.reason}）`).join('\n')
              + (result.failed.length > 5 ? '\n…' : '')
              + '\n\nもう一度選んでアップロードしてください。');
      } else {
        if (status) status.textContent = `${result.saved}枚入りました`;
        setTimeout(() => { if (box && !button.disabled) box.hidden = true; }, 2500);
      }
      if (onFinished) onFinished(result);
    });
  }

  window.TabiPhotoUpload = { uploadPhotos, wireUploader, MAX_BYTES };
})();
