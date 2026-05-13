(function() {
  'use strict';

  const TRANSLATION_MARKER = 'data-ko-translated';
  let config = {
    enabled: true,
    autoDetect: true,
    proxyUrl: 'http://127.0.0.1:8080'
  };

  function init() {
    loadConfig();
    observeChat();
  }

  function loadConfig() {
    chrome.runtime.sendMessage({ action: 'getConfig' }, (result) => {
      if (result) {
        config = { ...config, ...result };
      }
    });
  }

  function observeChat() {
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((node) => {
          if (node.nodeType === Node.ELEMENT_NODE) {
            handleNewNode(node);
          }
        });
      });
    });

    const chatContainer = document.querySelector('[data-chat-area]') ||
                          document.querySelector('.chat-container') ||
                          document.querySelector('main');

    if (chatContainer) {
      observer.observe(chatContainer, { childList: true, subtree: true });
    }

    setTimeout(() => {
      const existingMessages = document.querySelectorAll('[data-message]');
      existingMessages.forEach(handleMessage);
    }, 1000);
  }

  function handleNewNode(node) {
    if (node.hasAttribute && node.hasAttribute('data-message')) {
      handleMessage(node);
    }

    const messages = node.querySelectorAll && node.querySelectorAll('[data-message]');
    if (messages) {
      messages.forEach(handleMessage);
    }
  }

  async function handleMessage(element) {
    if (element.hasAttribute(TRANSLATION_MARKER)) {
      return;
    }

    const inputArea = element.querySelector('[data-message-input]') ||
                      element.querySelector('textarea') ||
                      element.querySelector('[contenteditable="true"]');

    if (inputArea) {
      inputArea.addEventListener('keydown', handleInput);
    }

    const assistantMessages = element.querySelectorAll('.assistant-message, [data-role="assistant"]');
    assistantMessages.forEach(handleAssistantMessage);
  }

  async function handleAssistantMessage(element) {
    if (element.hasAttribute(TRANSLATION_MARKER)) {
      return;
    }

    const originalText = element.textContent;
    if (!originalText || originalText.trim().length === 0) {
      return;
    }

    element.setAttribute(TRANSLATION_MARKER, 'pending');

    try {
      const translated = await translateText(originalText, 'en-ko');
      if (translated && translated !== originalText) {
        element.textContent = translated;
        element.setAttribute(TRANSLATION_MARKER, 'translated');
      }
    } catch (error) {
      console.error('Translation error:', error);
      element.setAttribute(TRANSLATION_MARKER, 'error');
    }
  }

  async function handleInput(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      const input = event.target;
      const text = input.value;

      if (text.trim().length === 0) {
        return;
      }

      if (containsKorean(text)) {
        event.preventDefault();

        try {
          const translated = await translateText(text, 'ko-en');
          input.value = translated;
        } catch (error) {
          console.error('Input translation error:', error);
        }
      }
    }
  }

  function containsKorean(text) {
    const koreanRegex = /[\uAC00-\uD7A3]/g;
    const koreanChars = text.match(koreanRegex) || [];
    const totalAlpha = text.replace(/[^a-zA-Z\uAC00-\uD7A3]/g, '').length;

    if (totalAlpha === 0) {
      return false;
    }

    return (koreanChars.length / totalAlpha) > 0.3;
  }

  async function translateText(text, direction) {
    const response = await chrome.runtime.sendMessage({
      action: 'translate',
      text,
      direction
    });

    if (response.success) {
      return response.result;
    } else {
      throw new Error(response.error);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();