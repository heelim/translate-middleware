const CONFIG_KEY = 'ko_translate_config';
const DEFAULT_CONFIG = {
  enabled: true,
  proxyUrl: 'http://127.0.0.1:8080',
  autoDetect: true,
  direction: 'auto',
  logLevel: 'info'
};

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get(CONFIG_KEY, (result) => {
    if (!result[CONFIG_KEY]) {
      chrome.storage.local.set({ [CONFIG_KEY]: DEFAULT_CONFIG });
    }
  });
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'getConfig') {
    chrome.storage.local.get(CONFIG_KEY, (result) => {
      sendResponse(result[CONFIG_KEY] || DEFAULT_CONFIG);
    });
    return true;
  }

  if (message.action === 'setConfig') {
    chrome.storage.local.set({ [CONFIG_KEY]: message.config }, () => {
      sendResponse({ success: true });
    });
    return true;
  }

  if (message.action === 'translate') {
    handleTranslate(message.text, message.direction)
      .then(result => sendResponse({ success: true, result }))
      .catch(error => sendResponse({ success: false, error: error.message }));
    return true;
  }
});

async function handleTranslate(text, direction) {
  const config = await getConfig();

  if (!config.enabled) {
    return text;
  }

  const targetLang = direction === 'ko-en' ? 'en' : 'ko';
  const sourceLang = direction === 'ko-en' ? 'ko' : 'en';

  try {
    const response = await fetch(`${config.proxyUrl}/v1/translate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        text,
        source_lang: sourceLang,
        target_lang: targetLang,
      }),
    });

    if (!response.ok) {
      throw new Error(`Translation failed: ${response.status}`);
    }

    const data = await response.json();
    return data.translated;
  } catch (error) {
    console.error('Translation error:', error);
    return text;
  }
}

function getConfig() {
  return new Promise((resolve) => {
    chrome.storage.local.get(CONFIG_KEY, (result) => {
      resolve(result[CONFIG_KEY] || DEFAULT_CONFIG);
    });
  });
}

chrome.proxy.settings.get({ incognito: false }, (config) => {
  console.log('Proxy configuration:', config);
});