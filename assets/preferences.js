/* Presentation-only preferences. Never change stored requests or listing data. */
(() => {
  'use strict';
  const root = document.documentElement;
  const read = key => { try { return localStorage.getItem(key); } catch { return null; } };
  const save = (key, value) => { try { localStorage.setItem(key, value); } catch {} };
  let language = read('radar-language') === 'en' ? 'en' : 'ar';
  let theme = read('radar-theme') === 'dark' ? 'dark' : 'light';
  let skin = ['radar', 'studio', 'terminal'].includes(read('radar-skin')) ? read('radar-skin') : 'radar';
  let dictionary = {}, entries = [], pending = false;
  const originals = new WeakMap(), attributes = new WeakMap(), translationCache = new Map();
  const excluded = element => element.closest('script,style,textarea,input,[contenteditable="true"],.display-controls');
  function translate(value) {
    if (!/[\u0600-\u06ff]/.test(value)) return value;
    if (translationCache.has(value)) return translationCache.get(value);
    const trimmed = value.trim();
    if (dictionary[trimmed]) return value.replace(trimmed, dictionary[trimmed]);
    // Only translate known UI phrases; unknown source text remains intact.
    let result = value;
    for (const [pattern, en] of entries) result = result.replace(pattern, () => en);
    if (translationCache.size > 5000) translationCache.clear();
    translationCache.set(value, result);
    return result;
  }
  function apply() {
    observer.disconnect();
    // Preserve implicit option values before translating their visible labels.
    document.querySelectorAll('option:not([value])').forEach(option => option.setAttribute('value', option.textContent));
    root.lang = language; root.dir = language === 'en' ? 'ltr' : 'rtl'; root.dataset.theme = theme; root.dataset.skin = skin;
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
    const en = language === 'en';
    lang.innerHTML = '<span aria-hidden="true" class="control-icon">◎</span><span>' + (en ? 'العربية' : 'English') + '</span>';
    lang.lang = en ? 'ar' : 'en';
    lang.setAttribute('aria-label', en ? 'Switch to Arabic' : 'التبديل إلى الإنجليزية');
    mode.innerHTML = '<span aria-hidden="true" class="control-icon">' + (theme === 'dark' ? '☀' : '☾') + '</span><span>' + (theme === 'dark' ? (en ? 'Day' : 'نهاري') : (en ? 'Night' : 'ليلي')) + '</span>';
    mode.setAttribute('aria-label', en ? (theme === 'dark' ? 'Switch to day mode' : 'Switch to night mode') : (theme === 'dark' ? 'تفعيل الوضع النهاري' : 'تفعيل الوضع الليلي'));
    mode.setAttribute('aria-pressed', String(theme === 'dark'));
    const skinNames = en ? {radar:'Radar',studio:'Studio',terminal:'Terminal'} : {radar:'رادار',studio:'استوديو',terminal:'تيرمنال'};
    const skinDescriptions = en ? {radar:'Fluid · navy & mint',studio:'Editorial · ivory & wine',terminal:'Technical · graphite & lime'} : {radar:'انسيابي · كحلي ونعناعي',studio:'تحريري · عاجي وعنابي',terminal:'تقني · رمادي وليموني'};
    document.getElementById('appearanceLabel').textContent = en ? 'Style' : 'الثيم';
    document.getElementById('currentSkin').textContent = skinNames[skin];
    document.getElementById('appearanceTitle').textContent = en ? 'Make it yours' : 'اختر طابعك';
    document.getElementById('appearanceHint').textContent = en ? 'Three complete styles. Day and night for each.' : 'ثلاثة تصاميم كاملة. نهاري وليلي لكل تصميم.';
    document.getElementById('appearanceClose').setAttribute('aria-label', en ? 'Close appearance settings' : 'إغلاق إعدادات المظهر');
    document.getElementById('appearanceToggle').setAttribute('aria-label', en ? 'Choose page style' : 'اختيار ثيم الصفحة');
    document.querySelector('.display-controls').setAttribute('aria-label', en ? 'Language and appearance' : 'اللغة والمظهر');
    document.querySelectorAll('[data-skin-choice]').forEach(button => {
      const key = button.dataset.skinChoice;
      button.querySelector('b').textContent = skinNames[key];
      button.querySelector('small').textContent = skinDescriptions[key];
      button.setAttribute('aria-pressed', String(skin === key));
    });
    document.querySelector('meta[name="theme-color"]').content = theme === 'dark' ? '#10161D' : '#F4F6FA';
    observer.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['placeholder', 'title', 'aria-label', 'alt'] });
  }
  const observer = new MutationObserver(() => {
    if (pending) return;
    pending = true; queueMicrotask(() => { pending = false; apply(); });
  });
  document.getElementById('languageToggle').addEventListener('click', () => { language = language === 'ar' ? 'en' : 'ar'; save('radar-language', language); apply(); });
  document.getElementById('themeToggle').addEventListener('click', () => { theme = theme === 'light' ? 'dark' : 'light'; save('radar-theme', theme); apply(); });
  const toggle = document.getElementById('appearanceToggle'), panel = document.getElementById('appearancePanel');
  function setPanel(open) { panel.hidden = !open; toggle.setAttribute('aria-expanded', String(open)); if (open) panel.querySelector('[aria-pressed="true"]')?.focus(); }
  toggle.addEventListener('click', () => setPanel(panel.hidden));
  document.getElementById('appearanceClose').addEventListener('click', () => { setPanel(false); toggle.focus(); });
  document.querySelectorAll('[data-skin-choice]').forEach(button => button.addEventListener('click', () => { skin = button.dataset.skinChoice; save('radar-skin', skin); apply(); }));
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !panel.hidden) { setPanel(false); toggle.focus(); } });
  document.addEventListener('click', event => { if (!event.target.closest('.display-controls')) setPanel(false); });
  apply();
  fetch('assets/translations-en.json?v=20261019-3').then(response => { if (!response.ok) throw new Error('Translation unavailable'); return response.json(); }).then(data => {
    dictionary = data; translationCache.clear(); entries = Object.entries(data).sort((a, b) => b[0].length - a[0].length).map(([ar, en]) => [new RegExp('(?<![\\p{L}])' + ar.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(?![\\p{L}])', 'gu'), en]); apply();
  }).catch(() => { language = 'ar'; apply(); });
})();
