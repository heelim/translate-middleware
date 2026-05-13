document.addEventListener('DOMContentLoaded', () => {
  const enabledCheckbox = document.getElementById('enabled');
  const autoDetectCheckbox = document.getElementById('autoDetect');
  const proxyUrlInput = document.getElementById('proxyUrl');
  const directionSelect = document.getElementById('direction');
  const statusSpan = document.getElementById('status');
  const saveButton = document.getElementById('save');

  loadConfig();

  saveButton.addEventListener('click', saveConfig);

  function loadConfig() {
    chrome.runtime.sendMessage({ action: 'getConfig' }, (config) => {
      if (config) {
        enabledCheckbox.checked = config.enabled !== false;
        autoDetectCheckbox.checked = config.autoDetect !== false;
        proxyUrlInput.value = config.proxyUrl || 'http://127.0.0.1:8080';
        directionSelect.value = config.direction || 'auto';
      }
    });
  }

  function saveConfig() {
    const config = {
      enabled: enabledCheckbox.checked,
      autoDetect: autoDetectCheckbox.checked,
      proxyUrl: proxyUrlInput.value,
      direction: directionSelect.value
    };

    chrome.runtime.sendMessage({ action: 'setConfig', config }, (response) => {
      if (response && response.success) {
        statusSpan.textContent = 'Saved!';
        statusSpan.style.color = '#00ff88';

        setTimeout(() => {
          statusSpan.textContent = 'Ready';
          statusSpan.style.color = '#00d4ff';
        }, 2000);
      } else {
        statusSpan.textContent = 'Error saving';
        statusSpan.style.color = '#ff4444';
      }
    });
  }
});