const chatBox = document.getElementById('chat-box');
  const messageForm = document.getElementById('message-form');
  const messageInput = document.getElementById('message-input');
  const sendButton = document.getElementById('send-button');
  const stopButton = document.getElementById('stop-button');
  const typingIndicator = document.getElementById('typing');

  let abortController = null;
  let currentRequestId = null;

  // 生成中の「考え中」表示：段階メッセージを巡回させて待ち時間を楽しく見せる
  const THINKING_STAGES = [
    '行き先を調べています', '交通を手配しています', '観光スポットを探しています',
    '宿を選んでいます', 'グルメを探しています', 'スケジュールを組んでいます', '仕上げています',
  ];
  let thinkingTimer = null;

  function startThinking() {
    const el = document.getElementById('thinking-text');
    let i = 0;
    if (el) el.textContent = THINKING_STAGES[0];
    typingIndicator.style.display = 'flex';
    if (thinkingTimer) clearInterval(thinkingTimer);
    thinkingTimer = setInterval(() => {
      i = (i + 1) % THINKING_STAGES.length;
      if (el) el.textContent = THINKING_STAGES[i];
    }, 2500);
  }

  function stopThinking() {
    typingIndicator.style.display = 'none';
    if (thinkingTimer) { clearInterval(thinkingTimer); thinkingTimer = null; }
  }

  // 会話の最初にメイトから話しかける挨拶（クライアント側で常に先頭に表示）
  const GREETING = 'こんにちは！旅のプランを一緒に考える「ちゃむ」です🍀\n\n'
    + '行き先・日程・人数・ご予算・やってみたいことなど、わかる範囲で教えてくださいね。ぴったりの旅行プランをご提案します。\n\n'
    + 'まずは、**どちらへ行ってみたいですか？**';

  function renderGreeting() {
    const el = createMessageElement('ai', GREETING);
    el.classList.add('greeting');
    chatBox.appendChild(el);
  }

  // エラーや接続断をユーザーに知らせる（無反応で止まったように見せない）
  function showSystemMessage(text) {
    chatBox.appendChild(createMessageElement('ai', text));
    chatBox.scrollTop = chatBox.scrollHeight;
  }

  // 失敗時に入力内容を送信欄へ戻す（そのまま再送信できるようにする）
  function restoreInput(message) {
    if (!messageInput.value) messageInput.value = message;
  }

  function generateId() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2);
  }

  function escapeHtml(text) {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

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

  // 停止ボタンが押された時の処理
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

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
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
              'うまくプランを作れませんでした。\n\n'
              + 'お手数ですが、もう一度「送信」ボタンを押してやり直してください（入力した内容はそのまま残してあります）。\n\n'
              + '繰り返し失敗するときは、行き先・日程・人数などをもう少し具体的に書き換えると通りやすくなります🍀'
            );
            restoreInput(message);
          }
        }
      }

      // OK/ABORTED/ERROR を一度も受け取らずに切れた場合（接続断・タイムアウト等）
      if (!settled) {
        showSystemMessage(
          '完了までに時間がかかりすぎたか、通信が途切れたようです。\n\n'
          + 'もう一度「送信」ボタンを押してお試しください（入力した内容はそのまま残してあります）。電波の良い場所だと安定します。\n\n'
          + 'それでも続くときは、少し時間をおいてからお試しください🍀'
        );
        restoreInput(message);
      }
    } catch (error) {
      if (error.name !== 'AbortError') {
        console.error('Error:', error);
        showSystemMessage(
          '通信エラーが発生しました。\n\n'
          + 'ネットワーク接続を確認して、もう一度「送信」ボタンを押してください（入力した内容はそのまま残してあります）。\n\n'
          + 'Wi-Fiやモバイル回線が安定した場所だと成功しやすいです🍀'
        );
        restoreInput(message);
      }
    } finally {
      messageInput.disabled = false;
      sendButton.style.display = 'flex';
      stopButton.style.display = 'none';
      stopThinking();
      messageInput.focus();
      abortController = null;
      currentRequestId = null;
    }
  });

  // 保存ボタンのクリック処理（動的に追加される要素に対応）
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

  document.getElementById('new-chat-btn').addEventListener('click', async () => {
    if (!confirm('チャット履歴をリセットして新しい会話を始めますか？')) return;
    await fetch('/reset_chat', { method: 'POST' });
    chatBox.innerHTML = '';
    renderGreeting();
  });

  renderGreeting();
  loadMessages();
