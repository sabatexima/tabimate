const chatBox = document.getElementById('chat-box');
  const messageForm = document.getElementById('message-form');
  const messageInput = document.getElementById('message-input');
  const sendButton = document.getElementById('send-button');
  const stopButton = document.getElementById('stop-button');
  const typingIndicator = document.getElementById('typing');

  let abortController = null;
  let currentRequestId = null;

  // 会話の最初にメイトから話しかける挨拶（クライアント側で常に先頭に表示）
  const GREETING = 'こんにちは！旅のプランを一緒に考えるメイトだうぱ🦎\n\n'
    + '行き先・日程・人数・予算・やりたいことなどを教えてくれたら、ぴったりの旅行プランを作るうぱ！\n\n'
    + 'まずは、**どこに行きたい？**';

  function renderGreeting() {
    const el = createMessageElement('ai', GREETING);
    el.classList.add('greeting');
    chatBox.appendChild(el);
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
    label.textContent = role === 'user' ? 'あなた' : 'メイト 🦎';
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
    typingIndicator.style.display = 'block';

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

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // 末尾の不完全な行を次回に持ち越す

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = JSON.parse(line.slice(6));
          if (data.status === 'OK' || data.status === 'ABORTED') {
            await loadMessages(true);
          }
        }
      }
    } catch (error) {
      if (error.name !== 'AbortError') {
        console.error('Error:', error);
      }
    } finally {
      messageInput.disabled = false;
      sendButton.style.display = 'flex';
      stopButton.style.display = 'none';
      typingIndicator.style.display = 'none';
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
