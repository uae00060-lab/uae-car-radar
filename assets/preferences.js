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
  let dismissed;
  try { dismissed = new Set(JSON.parse(read('radar-dismissed-notices') || '[]')); } catch { dismissed = new Set(); }
  const originals = new WeakMap(), attributes = new WeakMap(), translationCache = new Map();
  const excluded = element => element.closest('script,style,textarea,input,[contenteditable="true"],.notice-dismiss') || (element.closest('.display-controls') && !element.closest('#problemBox'));
  const templates = [
    [/أقل من تقدير الإعلانات المشابهة بنحو (\d+)٪/g, 'About $1% below the estimate from similar listings'],
    [/المقارنة من (\d+) إعلانًا، وليست تقييم فحص للسيارة/g, 'Compared with $1 listings; not an inspection of the car'],
    [/نشر حديث: ([\d-]+)/g, 'Recently posted: $1'],
    [/فحص خفيف كل ساعة عند الدقيقة 17، إضافة إلى جولات البحث\. قد تتأخر مهام GitHub؛ ليس رصدًا لحظيًا\. إعلان منشور خلال آخر يومين، وتحقق لا يتجاوز 6 ساعات\. نستبعد المباعة والمحجوزة والتعديلات التي رصدناها\. لا نستنتج مهنة البائع من التعديل\. آخر تقييم: /g,
      'A light check every hour at minute 17, in addition to search rounds. GitHub tasks may be delayed; this is not real-time monitoring. Ads posted in the last two days, checked within 6 hours. Sold, reserved and edited ads we detected are excluded. We never infer the seller\'s profession from an edit. Last evaluation: '],
    [/الإعلان يذكر: /g, 'The ad states: ']
  ];
  function translate(value) {
    if (!/[\u0600-\u06ff]/.test(value)) return value;
    if (translationCache.has(value)) return translationCache.get(value);
    const trimmed = value.trim();
    if (dictionary[trimmed]) return value.replace(trimmed, dictionary[trimmed]);
    // Only translate known UI phrases; unknown source text remains intact.
    let result = value;
    // Sentences built with numbers or dates (engine reasons, status lines) are translated whole first,
    // so word-by-word replacement never leaves a half-Arabic sentence.
    for (const [pattern, en] of templates) result = result.replace(pattern, en);
    for (const [pattern, en] of entries) result = result.replace(pattern, () => en);
    if (translationCache.size > 5000) translationCache.clear();
    translationCache.set(value, result);
    return result;
  }
  function apply() {
    observer.disconnect();
    document.querySelectorAll('#problemBox li').forEach(item => {
      if (!item.dataset.noticeKey) item.dataset.noticeKey = item.textContent.trim();
      item.hidden = dismissed.has(item.dataset.noticeKey);
      if (!item.querySelector('.notice-dismiss')) {
        const close = document.createElement('button'); close.type = 'button'; close.className = 'notice-dismiss'; close.textContent = '×';
        close.addEventListener('click', () => { dismissed.add(item.dataset.noticeKey); save('radar-dismissed-notices', JSON.stringify([...dismissed].slice(-100))); apply(); });
        item.append(close);
      }
    });
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
    lang.innerHTML = '<span class="language-abbr">' + (en ? 'ع' : 'EN') + '</span>';
    lang.lang = en ? 'ar' : 'en';
    lang.setAttribute('aria-label', en ? 'Switch to Arabic' : 'التبديل إلى الإنجليزية');
    mode.innerHTML = '<span aria-hidden="true" class="control-icon">' + (theme === 'dark' ? '☀' : '☾') + '</span><span>' + (theme === 'dark' ? (en ? 'Day' : 'نهاري') : (en ? 'Night' : 'ليلي')) + '</span>';
    mode.setAttribute('aria-label', en ? (theme === 'dark' ? 'Switch to day mode' : 'Switch to night mode') : (theme === 'dark' ? 'تفعيل الوضع النهاري' : 'تفعيل الوضع الليلي'));
    mode.setAttribute('aria-pressed', String(theme === 'dark'));
    const skinNames = en ? {radar:'Radar',studio:'Studio',terminal:'Terminal'} : {radar:'رادار',studio:'استوديو',terminal:'تيرمنال'};
    const skinDescriptions = en ? {radar:'Fluid · navy & mint',studio:'Editorial · ivory & bronze',terminal:'Technical · graphite & ice'} : {radar:'انسيابي · كحلي ونعناعي',studio:'تحريري · عاجي وبرونزي',terminal:'تقني · جرافيت وأزرق جليدي'};
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
    const count = document.querySelectorAll('#problemBox li:not([hidden])').length;
    const badge = document.getElementById('notificationCount'); badge.textContent = count > 9 ? '9+' : String(count); badge.hidden = !count;
    document.getElementById('notificationsEmpty').hidden = count > 0;
    document.getElementById('notificationsTitle').textContent = en ? 'Notifications' : 'الإشعارات';
    document.getElementById('notificationsHint').textContent = en ? 'Platform status and search alerts' : 'حالة المنصات وتنبيهات البحث';
    document.getElementById('notificationsEmpty').textContent = en ? 'You are all caught up' : 'لا توجد تنبيهات جديدة';
    document.getElementById('notificationsToggle').setAttribute('aria-label', en ? 'Notifications' : 'الإشعارات');
    document.getElementById('notificationsClose').setAttribute('aria-label', en ? 'Close notifications' : 'إغلاق الإشعارات');
    document.querySelectorAll('.notice-dismiss').forEach(button => button.setAttribute('aria-label', en ? 'Dismiss this notification' : 'إغلاق هذا التنبيه'));
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
  function setPanel(open) { if (open) setNotifications(false); panel.hidden = !open; toggle.setAttribute('aria-expanded', String(open)); if (open) panel.querySelector('[aria-pressed="true"]')?.focus(); }
  const notificationsButton = document.getElementById('notificationsToggle'), notificationsPanel = document.getElementById('notificationsPanel');
  function setNotifications(open) { notificationsPanel.hidden = !open; notificationsButton.setAttribute('aria-expanded', String(open)); if (open) { panel.hidden = true; toggle.setAttribute('aria-expanded', 'false'); } }
  notificationsButton.addEventListener('click', () => setNotifications(notificationsPanel.hidden));
  document.getElementById('notificationsClose').addEventListener('click', () => { setNotifications(false); notificationsButton.focus(); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !notificationsPanel.hidden) { setNotifications(false); notificationsButton.focus(); } });
  toggle.addEventListener('click', () => setPanel(panel.hidden));
  document.getElementById('appearanceClose').addEventListener('click', () => { setPanel(false); toggle.focus(); });
  document.querySelectorAll('[data-skin-choice]').forEach(button => button.addEventListener('click', () => { skin = button.dataset.skinChoice; save('radar-skin', skin); apply(); }));
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !panel.hidden) { setPanel(false); toggle.focus(); } });
  document.addEventListener('click', event => { if (!event.target.closest('.display-controls')) { setPanel(false); setNotifications(false); } });
  apply();
  fetch('assets/translations-en.json?v=20261019-6').then(response => { if (!response.ok) throw new Error('Translation unavailable'); return response.json(); }).then(data => {
    dictionary = data; translationCache.clear(); entries = Object.entries(data).sort((a, b) => b[0].length - a[0].length).map(([ar, en]) => [new RegExp('(?<![\\p{L}])' + ar.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(?![\\p{L}])', 'gu'), en]); apply();
  }).catch(() => { language = 'ar'; apply(); });
})();
