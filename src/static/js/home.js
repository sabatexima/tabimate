/* プラン作成チャット（home.html）。このアプリで一番こみいったファイル。

   ■ 送信の流れ
     フォーム送信 → POST /send_message → サーバーは SSE（data: 行）を流す
     → 最後に OK / ABORTED / ERROR のどれかが来たら、履歴を読み直して描き直す

   ■ ここで一番大事なこと: 生成はこの接続より長生きする
     プラン生成には数分かかる。サーバーは別スレッドで作り、**保存もそのスレッドが
     行う**ので、途中でブラウザを閉じてもリロードしても結果は残る。
     （以前は SSE の送信側で保存していて、リロードした瞬間に生成が捨てられていた）

   ■ だから、リロード後の復元がある（resumeIfGenerating）
     まだ返事待ちの生成があるかどうかは**サーバーが知っている**。ページを出すとき
     .chat-container の data-pending-request / data-pending-message に載せてくるので、
     それを読むだけでよい。localStorage に控えは持たない（端末とサーバーがずれるため）。
     SSE には繋ぎ直せないので、完了は /generation_status に問い合わせて知る。

   ■ 状態はこの3つだけ
     currentRequestId  いま走っている生成の id（null なら何も走っていない）
     abortController   受信を打ち切るためのもの
     resumePoll        復元中の定期確認。**止め忘れると前の回の結果が割り込む**
     この3つは resetGenerationState() で必ずまとめて戻す。

   ■ 注意
     このファイルは関数で囲っていないので、ここの const / let はページ全体で共有される。
     テンプレート側に同じ名前があるとスクリプトごと SyntaxError で死ぬ（実際に起きた。
     tests/test_static_js.py が見張っている）。 */

const chatBox = document.getElementById('chat-box');
  const messageForm = document.getElementById('message-form');
  const messageInput = document.getElementById('message-input');
  const sendButton = document.getElementById('send-button');
  const stopButton = document.getElementById('stop-button');
  const typingIndicator = document.getElementById('typing');

  let abortController = null;
  let currentRequestId = null;
  // リロード復元の定期確認。止め忘れると、新しい相談を始めたあとに
  // 前の回の結果が割り込んでくる
  let resumePoll = null;

  // 生成中の段階表示。先頭(ご希望の読み取り)は条件の質問など短い応答もカバーし、
  // 長い生成のときだけ交通→観光→…と前へ進め、最後で止める（ループしない＝進捗に見える）。
  const THINKING_STAGES = [
    '🍀 ご希望を読み取っています',
    '🚄 交通を調べています',
    '🗺 観光スポットを選んでいます',
    '🏨 宿を選んでいます',
    '🍱 グルメを探しています',
    '📅 スケジュールを組み立て中',
    '✨ 仕上げています',
  ];
  let thinkingTimer = null;

  // 「考えています」を出し、段階表示を進め始める
  function startThinking() {
    const el = document.getElementById('thinking-text');
    let i = 0;
    if (el) el.textContent = THINKING_STAGES[0];
    typingIndicator.style.display = 'flex';
    if (thinkingTimer) clearInterval(thinkingTimer);
    // 約5秒ごとに次の段階へ前進。最後（仕上げ）に達したら止める。
    // 条件の質問など短い応答は最初の段階のまま終わるので、誤った段階を見せない。
    thinkingTimer = setInterval(() => {
      if (i < THINKING_STAGES.length - 1) {
        i++;
        if (el) el.textContent = THINKING_STAGES[i];
      }
      if (i >= THINKING_STAGES.length - 1) {
        clearInterval(thinkingTimer);
        thinkingTimer = null;
      }
    }, 5000);
  }

  function stopThinking() {
    typingIndicator.style.display = 'none';
    if (thinkingTimer) { clearInterval(thinkingTimer); thinkingTimer = null; }
  }

  // 会話の最初にメイトから話しかける挨拶（クライアント側で常に先頭に表示）
  const GREETING = 'こんにちは！旅のプランを一緒に考える「ちゃむ」です🍀\n\n'
    + '行き先・日程・人数・ご予算・やってみたいことなど、わかる範囲で教えてくださいね。ぴったりの旅行プランをご提案します。\n\n'
    + 'まずは、**どちらへ行ってみたいですか？**';

  // 挨拶はDBに保存せず、毎回この場で先頭に足す。保存すると履歴が1件増えて
  // 「新しいチャット」の確認や件数の比較がずれる
  function renderGreeting() {
    const el = createMessageElement('ai', GREETING);
    el.classList.add('greeting');
    chatBox.appendChild(el);
  }

  // エラーや接続断をユーザーに知らせる（無反応で止まったように見せない）。
  // retryMessage を渡すと「もう一度ためす」ボタンを添え、その文をそのまま再送する。
  function showSystemMessage(text, retryMessage) {
    const el = createMessageElement('ai', text);
    if (retryMessage) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'retry-btn';
      btn.textContent = '🍀 もう一度ためす';
      btn.addEventListener('click', () => {
        btn.disabled = true;
        messageInput.value = retryMessage;
        submitForm();
      });
      el.appendChild(btn);
    }
    chatBox.appendChild(el);
    chatBox.scrollTop = chatBox.scrollHeight;
  }

  // 失敗時に入力内容を送信欄へ戻す（そのまま再送信できるようにする）
  function restoreInput(message) {
    if (!messageInput.value) messageInput.value = message;
  }

  // フォームの submit を programmatic に起こす（?q= からの自動送信・再送で使う）。
  // requestSubmit があればそちらを使い、無いブラウザには Event で代替する
  function submitForm() {
    if (messageForm.requestSubmit) messageForm.requestSubmit();
    else messageForm.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
  }

  // 生成まわりの状態を初期に戻す。入力欄・ボタン・控えを一箇所でまとめて戻すことで、
  // 「送信が終わったのに入力欄が押せないまま」のような取り残しを防ぐ。
  function resetGenerationState() {
    currentRequestId = null;
    abortController = null;
    messageInput.disabled = false;
    sendButton.style.display = 'flex';
    stopButton.style.display = 'none';
    stopThinking();
    if (resumePoll) { clearInterval(resumePoll); resumePoll = null; }
  }

  // 走っている生成を止める。サーバーに知らせてから、こちらの受信も打ち切る。
  async function abortCurrentGeneration() {
    if (!currentRequestId) return;
    try {
      await fetch('/abort_request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: `request_id=${encodeURIComponent(currentRequestId)}`,
      });
    } catch (e) { /* 通知できなくても、こちら側は止める */ }
    if (abortController) {
      try { abortController.abort(); } catch (e) { /* noop */ }
    }
  }

  // 確認を出すかどうかはサーバーの履歴で決める。
  // 画面はまだ描き終えていないことがあるので、DOM の件数はあてにならない。
  async function hasStoredMessages() {
    try {
      const res = await fetch('/get_messages');
      if (!res.ok) return false;
      const msgs = await res.json();
      return Array.isArray(msgs) && msgs.length > 0;
    } catch (e) {
      return false;
    }
  }

  // 「新しいチャット」の一連の動作。?q= から来たときも同じ道を通す。
  //
  // 生成中に押されることがあるので、まず止めてから消す。止めずに履歴だけ消すと、
  // 走っている生成があとから返事だけを書き込み、質問の無い会話ができてしまう。
  // リセットに失敗したときは画面を消さない。消すと、サーバーには残っているのに
  // 消えたように見えて、次に開いたとき履歴が戻ってきて驚くことになる。
  async function startNewChat() {
    const generating = currentRequestId !== null;
    if (generating || await hasStoredMessages()) {
      const question = generating
        ? '作成中のプランを取りやめて、新しい相談を始めますか？'
        : 'チャット履歴をリセットして新しい会話を始めますか？';
      if (!confirm(question)) return false;
    }

    await abortCurrentGeneration();

    let reset = false;
    try {
      reset = (await fetch('/reset_chat', { method: 'POST' })).ok;
    } catch (e) {
      reset = false;
    }

    resetGenerationState();
    if (!reset) {
      showSystemMessage(
        '履歴をリセットできませんでした。\n\n'
        + '通信を確かめて、もう一度お試しください🍀'
      );
      return false;
    }

    chatBox.innerHTML = '';
    renderGreeting();
    messageInput.value = '';
    messageInput.focus();
    return true;
  }

  // ホームの「こんな旅はどう？」から ?q= で来たときの受け口。
  // 新しい相談として始めたいので、履歴をリセットしてからその文を送る。
  async function consumeQueryPrompt() {
    const q = new URLSearchParams(location.search).get('q');
    if (!q) return;
    history.replaceState(null, '', location.pathname);  // 再読込での二重送信を防ぐ
    if (!await startNewChat()) return;                  // 断られたら何もしない
    messageInput.value = q;
    submitForm();
  }

  // 生成1回ぶんの id。サーバーはこれで「どの生成か」を追い、中断や状態問い合わせに使う。
  // 時刻＋乱数で、同じ人が連続で送っても衝突しない程度あれば足りる
  function generateId() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2);
  }

  // 吹き出し1つを組み立てる。自分の発言は textContent（そのまま文字として）、
  // ちゃむの返事は Markdown → HTML に変換してから DOMPurify で洗う。
  // プランカードは <details> と data-plan を使うので、消されないよう許可を足している
  function createMessageElement(role, content) {
    const wrapper = document.createElement('div');
    wrapper.classList.add('message-wrapper');
    wrapper.classList.add(role === 'user' ? 'user-message-wrapper' : 'ai-message-wrapper');

    const label = document.createElement('div');
    label.classList.add('avatar-label');
    if (role === 'user') {
      label.textContent = 'あなた';
    } else {
      const icon = document.createElement('img');
      icon.src = '/static/img/mate-head.png';
      icon.alt = '';
      icon.classList.add('mate-avatar');
      label.appendChild(icon);
      label.appendChild(document.createTextNode('ちゃむ'));
    }
    wrapper.appendChild(label);

    const messageElement = document.createElement('div');
    messageElement.classList.add('message');
    messageElement.classList.add(role === 'user' ? 'user-message' : 'ai-message');
    if (role === 'user') {
      messageElement.textContent = content;
    } else {
      messageElement.innerHTML = DOMPurify.sanitize(marked.parse(content), { ADD_TAGS: ['details', 'summary'], ADD_ATTR: ['data-plan', 'class', 'open'] });
    }
    wrapper.appendChild(messageElement);

    return wrapper;
  }

  // サーバーの履歴で会話を描き直す（差分ではなく、毎回まるごと作り直す）。
  // 件数が同じなら何もしないのは、無駄な再描画でスクロール位置が飛ばないため。
  // 生成が終わった直後は中身が変わっているので forceScroll=true で必ず描き直す
  async function loadMessages(forceScroll = false) {
    try {
      const response = await fetch('/get_messages');
      const messages = await response.json();
      const currentMsgCount = chatBox.querySelectorAll('.message-wrapper:not(.greeting)').length;
      if (!forceScroll && messages.length === currentMsgCount) return;

      chatBox.innerHTML = '';
      renderGreeting();
      messages.forEach(msg => {
        chatBox.appendChild(createMessageElement(msg.role, msg.content));
      });
      chatBox.scrollTop = chatBox.scrollHeight;
    } catch (error) {
      console.error('Failed to load messages:', error);
    }
  }

  // 停止ボタン。サーバーに「やめて」とだけ伝え、受信は切らない。
  // ここで abort すると ABORTED イベントを受け取れず、画面が中途半端に残る
  stopButton.addEventListener('click', async () => {
    if (currentRequestId) {
      // サーバーに中断を通知（SSEストリームはそのまま維持し、ABORTEDイベントを待つ）
      fetch('/abort_request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: `request_id=${encodeURIComponent(currentRequestId)}`
      }).catch(() => {});
    }
  });

  // 送信。ここが本体
  messageForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const message = messageInput.value.trim();
    if (!message) return;

    currentRequestId = generateId();

    messageInput.disabled = true;
    sendButton.style.display = 'none';
    stopButton.style.display = 'flex';
    startThinking();

    chatBox.appendChild(createMessageElement('user', message));
    chatBox.scrollTop = chatBox.scrollHeight;
    messageInput.value = '';

    abortController = new AbortController();

    try {
      const response = await fetch('/send_message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: `message=${encodeURIComponent(message)}&request_id=${currentRequestId}`,
        signal: abortController.signal,
      });

      // SSE 以外の即時エラー応答（429:レート制限 / 400:入力不備 / 5xx など）を先に処理する。
      // これらは data: イベントを返さないため、ストリームとして読むと誤って
      // 「通信が途切れた」表示になってしまう。
      if (!response.ok) {
        let serverMsg = '';
        try { serverMsg = (await response.json()).message || ''; } catch (e) { /* noop */ }
        if (response.status === 429) {
          showSystemMessage(
            serverMsg || '少し早すぎたみたいです🍀\n\n少し時間をおいてから、もう一度「送信」ボタンを押してください（入力した内容はそのまま残してあります）。'
          );
        } else {
          showSystemMessage(
            (serverMsg ? serverMsg + '\n\n' : 'うまく送信できませんでした。\n\n')
            + 'もう一度「送信」ボタンを押してお試しください（入力した内容はそのまま残してあります）🍀'
          );
        }
        restoreInput(message);
        return; // finally で入力欄は復帰する
      }

      // SSE を手で読む。EventSource を使わないのは、あれが GET しか投げられず、
      // 本文（メッセージ）を POST で送れないため
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      // 受信は行の途中で切れる。末尾の不完全な行を次の chunk まで持ち越す
      let buffer = '';
      let settled = false; // OK/ABORTED/ERROR のいずれかを受け取ったか

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // 末尾の不完全な行を次回に持ち越す

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          let data;
          try {
            data = JSON.parse(line.slice(6));
          } catch (e) {
            continue; // 不完全な行はスキップ
          }
          if (data.status === 'OK' || data.status === 'ABORTED') {
            settled = true;
            await loadMessages(true);
          } else if (data.status === 'ERROR') {
            settled = true;
            showSystemMessage(
              'うまくプランを作れませんでした…ごめんなさい🍀\n\n'
              + '下のボタンからもう一度お試しください。繰り返すときは、行き先・日程・人数などを少し具体的に書き換えると通りやすくなります。',
              message
            );
            restoreInput(message);
          }
        }
      }

      // OK/ABORTED/ERROR を一度も受け取らずに切れた場合（接続断・タイムアウト等）
      if (!settled) {
        showSystemMessage(
          '完了までに時間がかかりすぎたか、通信が途切れたようです。\n\n'
          + '電波の良い場所で、下のボタンからもう一度お試しください🍀',
          message
        );
        restoreInput(message);
      }
    } catch (error) {
      if (error.name !== 'AbortError') {
        console.error('Error:', error);
        showSystemMessage(
          '通信エラーが発生しました。\n\n'
          + 'ネットワークを確認して、下のボタンからもう一度お試しください🍀',
          message
        );
        restoreInput(message);
      }
    } finally {
      resetGenerationState();
      messageInput.focus();
    }
  });

  // リロード後、まだ返事を待っている生成があれば「作成中」表示を戻す。
  //
  // 誰が生成中かはサーバーが知っている。ページを出すときに
  // data-pending-request / data-pending-message に載せてくれるので、
  // それを読むだけでよい（端末側に控えを持たない）。
  // SSEストリームには繋ぎ直せないので、完了は問い合わせて知る。
  async function resumeIfGenerating() {
    const box = document.querySelector('.chat-container');
    const rid = box && box.dataset.pendingRequest;
    if (!rid) return;
    const askedMessage = (box.dataset.pendingMessage || '');

    // 作成中の見た目に戻す（停止ボタンも currentRequestId 経由で効く）
    currentRequestId = rid;
    messageInput.disabled = true;
    sendButton.style.display = 'none';
    stopButton.style.display = 'flex';
    startThinking();

    // 生成がどうなったかを尋ねる。
    //   'pending' まだ作っている最中
    //   'done'    返答が保存された（成功して終わった）
    //   'gone'    失敗か中断（その回の行はまとめて消えている）
    //   null      通信できなかった。決めつけずに次回へ回す
    const askState = async () => {
      try {
        const r = await fetch('/generation_status?request_id=' + encodeURIComponent(rid));
        // 401（セッション切れ）や 5xx を「もう終わった」と読み違えないこと。
        // 誤ると、まだ作っている最中なのに失敗の案内を出してしまう
        if (!r.ok) return null;
        const s = await r.json();
        if (s.state === 'pending' || s.state === 'done' || s.state === 'gone') return s.state;
        return s.active === true ? 'pending' : 'gone';  // 古い形の応答への保険
      } catch (e) { return null; }  // 判定不能
    };

    // 生成が終わったあとの後片付け。結果が残らなかった（エラー/中断）ときは
    // 質問文を入力欄に戻し、リロードしない時と同じ案内を出す。
    const finish = async (state) => {
      resetGenerationState();
      await loadMessages(true);
      if (state === 'done') {
        messageInput.focus();
        return;
      }
      restoreInput(askedMessage);
      showSystemMessage(
        '前回のプラン作成は最後まで終わりませんでした。\n'
        + 'お手数ですが、下のボタンからもう一度お試しください🍀',
        askedMessage
      );
    };

    let ticks = 0;
    resumePoll = setInterval(async () => {
      ticks += 1;
      const state = await askState();
      if (state === null) return;                     // 一時的な通信エラーは次回リトライ
      if (state === 'pending' && ticks < 360) return;  // まだ生成中（上限15分で強制解除）
      clearInterval(resumePoll);
      resumePoll = null;
      await finish(state);
    }, 2500);
  }

  // 「このプランを保存する」。ボタンは返事が届くたびに作られるので、
  // ボタン自体ではなく chatBox で受ける（動的に増える要素への定石）。
  // 送る中身は、サーバーが data-plan にJSONで埋めておいたものをそのまま返すだけ
  chatBox.addEventListener('click', async (e) => {
    const btn = e.target.closest('.plan-save-btn');
    if (!btn || btn.disabled) return;

    btn.disabled = true;
    btn.textContent = '保存中...';

    try {
      const plan = JSON.parse(btn.dataset.plan);
      const res = await fetch('/save_plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(plan),
      });
      const result = await res.json();
      if (result.status === 'OK') {
        btn.textContent = '✓ 保存しました';
        btn.classList.add('saved');
        if (window.cloverBurst) {
          const r = btn.getBoundingClientRect();
          window.cloverBurst(r.left + r.width / 2, r.top);
        }
      } else {
        btn.textContent = '保存に失敗しました';
        btn.disabled = false;
      }
    } catch (err) {
      btn.textContent = '保存に失敗しました';
      btn.disabled = false;
    }
  });

  const newChatBtn = document.getElementById('new-chat-btn');
  newChatBtn.addEventListener('click', async () => {
    // 押している間は塞ぐ（連打すると reset と abort が入り乱れる）
    newChatBtn.disabled = true;
    try {
      await startNewChat();
    } finally {
      newChatBtn.disabled = false;
    }
  });

  // 起動時の並び順は大事。履歴を描き終える前に復元処理を走らせると、
  // どちらも chatBox を作り直すので二重に描かれたり消えたりする。
  renderGreeting();
  (async () => {
    await loadMessages();
    await resumeIfGenerating();
    await consumeQueryPrompt();
  })();
