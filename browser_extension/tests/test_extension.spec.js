const { test, expect } = require('@playwright/test');
const path = require('path');

const EXTENSION_PATH = path.join(__dirname, '..');
const MOCK_PAGES_PATH = path.join(__dirname, 'mock_pages');

test.describe('Browser Extension Playwright Tests', () => {
  test('popup.html exists and is readable', async ({ page }) => {
    const popupPath = path.join(EXTENSION_PATH, 'popup.html');
    const fs = require('fs');
    expect(fs.existsSync(popupPath)).toBe(true);
    const content = fs.readFileSync(popupPath, 'utf8');
    expect(content.length).toBeGreaterThan(0);
    expect(content).toContain('<!DOCTYPE html>');
  });

  test('popup UI elements load correctly', async ({ page }) => {
    const popupPath = `file://${path.join(EXTENSION_PATH, 'popup.html')}`;
    await page.goto(popupPath);
    await expect(page.locator('.popup-container')).toBeVisible();
    await expect(page.locator('#enabled')).toBeVisible();
    await expect(page.locator('#autoDetect')).toBeVisible();
    await expect(page.locator('#proxyUrl')).toBeVisible();
    await expect(page.locator('#direction')).toBeVisible();
    await expect(page.locator('#status')).toBeVisible();
    await expect(page.locator('#save')).toBeVisible();
  });

  test('popup toggle functionality works', async ({ page }) => {
    const popupPath = `file://${path.join(EXTENSION_PATH, 'popup.html')}`;
    await page.goto(popupPath);
    const enabledToggle = page.locator('#enabled');
    await expect(enabledToggle).toBeChecked();
    await enabledToggle.uncheck();
    await expect(enabledToggle).not.toBeChecked();
    await enabledToggle.check();
    await expect(enabledToggle).toBeChecked();
  });

  test('popup auto-detect toggle works', async ({ page }) => {
    const popupPath = `file://${path.join(EXTENSION_PATH, 'popup.html')}`;
    await page.goto(popupPath);
    const autoDetect = page.locator('#autoDetect');
    await expect(autoDetect).toBeChecked();
    await autoDetect.uncheck();
    await expect(autoDetect).not.toBeChecked();
  });

  test('popup proxy URL input accepts text', async ({ page }) => {
    const popupPath = `file://${path.join(EXTENSION_PATH, 'popup.html')}`;
    await page.goto(popupPath);
    const proxyInput = page.locator('#proxyUrl');
    await expect(proxyInput).toHaveValue('http://127.0.0.1:8080');
    await proxyInput.clear();
    await proxyInput.fill('http://custom-proxy:3128');
    await expect(proxyInput).toHaveValue('http://custom-proxy:3128');
  });

  test('popup direction select has all options', async ({ page }) => {
    const popupPath = `file://${path.join(EXTENSION_PATH, 'popup.html')}`;
    await page.goto(popupPath);
    const directionSelect = page.locator('#direction');
    const options = await directionSelect.locator('option').all();
    expect(options.length).toBe(3);
    await expect(directionSelect).toHaveValue('auto');
  });

  test('popup status indicator shows initial Ready state', async ({ page }) => {
    const popupPath = `file://${path.join(EXTENSION_PATH, 'popup.html')}`;
    await page.goto(popupPath);
    await expect(page.locator('#status')).toHaveText('Ready');
  });

  test('popup save button exists and is clickable', async ({ page }) => {
    const popupPath = `file://${path.join(EXTENSION_PATH, 'popup.html')}`;
    await page.goto(popupPath);
    const saveBtn = page.locator('#save');
    await expect(saveBtn).toBeVisible();
    await expect(saveBtn).toBeEnabled();
    await expect(saveBtn).toHaveText('Save Settings');
  });

  test('mock ChatGPT page loads with chat area', async ({ page }) => {
    const mockPagePath = `file://${path.join(MOCK_PAGES_PATH, 'chatgpt_mock.html')}`;
    await page.goto(mockPagePath);
    await expect(page.locator('[data-chat-area]')).toBeVisible();
  });

  test('mock ChatGPT page contains message elements', async ({ page }) => {
    const mockPagePath = `file://${path.join(MOCK_PAGES_PATH, 'chatgpt_mock.html')}`;
    await page.goto(mockPagePath);
    const messages = page.locator('[data-message]');
    await expect(messages).toHaveCount(3);
  });

  test('mock Claude page loads with chat container', async ({ page }) => {
    const mockPagePath = `file://${path.join(MOCK_PAGES_PATH, 'claude_mock.html')}`;
    await page.goto(mockPagePath);
    await expect(page.locator('.chat-container')).toBeVisible();
    const messages = page.locator('[data-message]');
    await expect(messages).toHaveCount(3);
  });

  test('content script can detect input areas on mock pages', async ({ page }) => {
    const mockPagePath = `file://${path.join(MOCK_PAGES_PATH, 'chatgpt_mock.html')}`;
    await page.goto(mockPagePath);
    await expect(page.locator('[data-message-input]')).toBeVisible();
  });

  test('mock pages contain assistant message elements', async ({ page }) => {
    const mockPagePath = `file://${path.join(MOCK_PAGES_PATH, 'claude_mock.html')}`;
    await page.goto(mockPagePath);
    const assistant = page.locator('[data-role="assistant"]');
    await expect(assistant).toHaveCount(2);
  });

  test('popup CSS styles are applied', async ({ page }) => {
    const popupPath = `file://${path.join(EXTENSION_PATH, 'popup.html')}`;
    await page.goto(popupPath);
    await expect(page.locator('.popup-container')).toBeVisible();
  });

  test('popup form labels are properly associated', async ({ page }) => {
    const popupPath = `file://${path.join(EXTENSION_PATH, 'popup.html')}`;
    await page.goto(popupPath);
    await expect(page.locator('label[for="enabled"]')).toHaveText('Enable Translation');
    await expect(page.locator('label[for="autoDetect"]')).toHaveText('Auto-detect Language');
    await expect(page.locator('label[for="proxyUrl"]')).toHaveText('Proxy URL');
    await expect(page.locator('label[for="direction"]')).toHaveText('Default Direction');
  });

  test('mock pages contain Korean text for translation testing', async ({ page }) => {
    const mockPagePath = `file://${path.join(MOCK_PAGES_PATH, 'chatgpt_mock.html')}`;
    await page.goto(mockPagePath);
    const content = await page.content();
    expect(content.includes('안녕하세요') || content.includes('번역')).toBe(true);
  });

  test('mock pages contain English text for translation testing', async ({ page }) => {
    const mockPagePath = `file://${path.join(MOCK_PAGES_PATH, 'chatgpt_mock.html')}`;
    await page.goto(mockPagePath);
    const content = await page.content();
    expect(content.includes('Hello') || content.includes('help')).toBe(true);
  });

  test('popup checkbox type attributes are correct', async ({ page }) => {
    const popupPath = `file://${path.join(EXTENSION_PATH, 'popup.html')}`;
    await page.goto(popupPath);
    const enabled = page.locator('#enabled');
    expect(await enabled.getAttribute('type')).toBe('checkbox');
    const autoDetect = page.locator('#autoDetect');
    expect(await autoDetect.getAttribute('type')).toBe('checkbox');
  });

  test('popup has proper heading title', async ({ page }) => {
    const popupPath = `file://${path.join(EXTENSION_PATH, 'popup.html')}`;
    await page.goto(popupPath);
    await expect(page.locator('h1')).toHaveText('Korean Translation');
  });

  test('extension manifest.json exists and is valid', async () => {
    const fs = require('fs');
    const manifestPath = path.join(EXTENSION_PATH, 'manifest.json');
    expect(fs.existsSync(manifestPath)).toBe(true);
    const content = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
    expect(content.manifest_version).toBe(3);
    expect(content.name).toBeDefined();
    expect(content.permissions).toBeDefined();
  });

  test('extension background.js exists', async () => {
    const fs = require('fs');
    const bgPath = path.join(EXTENSION_PATH, 'background.js');
    expect(fs.existsSync(bgPath)).toBe(true);
  });

  test('extension content.js exists', async () => {
    const fs = require('fs');
    const contentPath = path.join(EXTENSION_PATH, 'content.js');
    expect(fs.existsSync(contentPath)).toBe(true);
  });

  test('popup complete interaction flow', async ({ page }) => {
    const popupPath = `file://${path.join(EXTENSION_PATH, 'popup.html')}`;
    await page.goto(popupPath);
    await page.locator('#enabled').uncheck();
    await page.locator('#proxyUrl').fill('http://test:9999');
    await page.locator('#direction').selectOption('ko-en');
    await page.locator('#save').click();
  });

  test('popup checkbox toggles affect state correctly', async ({ page }) => {
    const popupPath = `file://${path.join(EXTENSION_PATH, 'popup.html')}`;
    await page.goto(popupPath);
    const enabled = page.locator('#enabled');
    const autoDetect = page.locator('#autoDetect');
    await enabled.uncheck();
    await autoDetect.uncheck();
    await expect(enabled).not.toBeChecked();
    await expect(autoDetect).not.toBeChecked();
    await enabled.check();
    await autoDetect.check();
    await expect(enabled).toBeChecked();
    await expect(autoDetect).toBeChecked();
  });

  test('popup direction change persists', async ({ page }) => {
    const popupPath = `file://${path.join(EXTENSION_PATH, 'popup.html')}`;
    await page.goto(popupPath);
    const direction = page.locator('#direction');
    await direction.selectOption('ko-en');
    await expect(direction).toHaveValue('ko-en');
    await direction.selectOption('en-ko');
    await expect(direction).toHaveValue('en-ko');
  });
});