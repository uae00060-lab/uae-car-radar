/* Presentation-only preferences. Never change stored requests or listing data. */
(() => {
  'use strict';
  const root = document.documentElement;
  const read = key => { try { return localStorage.getItem(key); } catch { return null; } };
  const save = (key, value) => { try { localStorage.setItem(key, value); } catch {} };
  let language = read('radar-language') === 'en' ? 'en' : 'ar';
  let theme = read('radar-theme') === 'dark' ? 'dark' : 'light';
  let dictionary = {}, entries = [], pending = false;
  const originals = new WeakMap(), attributes = new WeakMap();
  const excluded = element => element.closest('script,style,textarea,input,[contenteditable="true"],.display-controls');
  function translate(value) {
    const trimmed = value.trim();
    if (dictionary[trimmed]) return value.replace(trimmed, dictionary[trimmed]);
    // Only translate known UI phrases; unknown source text remains intact.
    let result = value;
    for (const [pattern, en] of entries) result = result.replace(pattern, () => en);
    return result;
  }
  function apply() {
    observer.disconnect();
    // Preserve implicit option values before translating their visible labels.
    document.querySelectorAll('option:not([value])').forEach(option => option.setAttribute('value', option.textContent));
    root.lang = language; root.dir = language === 'en' ? 'ltr' : 'rtl'; root.dataset.theme = theme;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      if (!node.parentElement || excluded(node.parentElement)) continue;
      const previous = originals.get(node);
      const source = previous && node.nodeValue === previous.rendered ? previous.source : node.nodeValue;
      const rendered = language === 'en' ? translate(source) : source;
      originals.set(node, { source, rendered });
      if (node.nodeValue !== rendered) node.nodeValue = rendered;
    }
    document.querySelectorAll('[placeholder],[title],[aria-label],img[alt]').forEach(element => {
      if (excluded(element)) return;
      const saved = attributes.get(element) || {};
      for (const attr of ['placeholder', 'title', 'aria-label', 'alt']) {
        if (!element.hasAttribute(attr)) continue;
        const value = element.getAttribute(attr), previous = saved[attr];
        const source = previous && value === previous.rendered ? previous.source : value;
        const rendered = language === 'en' ? translate(source) : source;
        saved[attr] = { source, rendered };
        if (value !== rendered) element.setAttribute(attr, rendered);
      }
      attributes.set(element, saved);
    });
    document.title = language === 'en' ? 'UAE Car Radar' : 'رادار سيارات الإمارات';
    const lang = document.getElementById('languageToggle'), mode = document.getElementById('themeToggle');
    lang.textContent = language === 'ar' ? 'English' : 'العربية'; lang.lang = language === 'ar' ? 'en' : 'ar';
    lang.setAttribute('aria-label', language === 'ar' ? 'Switch to English' : 'التبديل إلى العربية');
    mode.textContent = theme === 'dark' ? (language === 'en' ? '☀ Day' : '☀ نهاري') : (language === 'en' ? '☾ Night' : '☾ ليلي');
    mode.setAttribute('aria-label', language === 'en' ? (theme === 'dark' ? 'Switch to day mode' : 'Switch to night mode') : (theme === 'dark' ? 'تفعيل الوضع النهاري' : 'تفعيل الوضع الليلي'));
    mode.setAttribute('aria-pressed', String(theme === 'dark'));
    document.querySelector('meta[name="theme-color"]').content = theme === 'dark' ? '#0B1220' : '#0B1732';
    observer.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['placeholder', 'title', 'aria-label', 'alt'] });
  }
  const observer = new MutationObserver(() => {
    if (pending) return;
    pending = true; queueMicrotask(() => { pending = false; apply(); });
  });
  document.getElementById('languageToggle').addEventListener('click', () => { language = language === 'ar' ? 'en' : 'ar'; save('radar-language', language); apply(); });
  document.getElementById('themeToggle').addEventListener('click', () => { theme = theme === 'light' ? 'dark' : 'light'; save('radar-theme', theme); apply(); });
  apply();
  fetch('assets/translations-en.json').then(response => { if (!response.ok) throw new Error('Translation unavailable'); return response.json(); }).then(data => {
    dictionary = data; entries = Object.entries(data).sort((a, b) => b[0].length - a[0].length).map(([ar, en]) => [new RegExp('(?<![\\p{L}])' + ar.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(?![\\p{L}])', 'gu'), en]); apply();
  }).catch(() => { language = 'ar'; apply(); });
})();
