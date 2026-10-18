# رادار سيارات الإمارات

بحث مجدول في منصات السيارات المستعملة في الإمارات، مع لوحة تحكم وتقارير PDF وإشعارات. يعمل كاملًا على GitHub مجانًا، ولا يعتمد على أي اشتراك.

**الرابط:** `https://uae00060-lab.github.io/uae-car-radar/`

## ما يفعله

- يبحث في يلا موتور، وDubiCars، وCarSwitch، وAUTO.AE، وOneClickDrive، والسوق المفتوح، ودوبيزل (انظر «حدود معروفة»). روابط قسم مرجان المستخدمة أعادت 404 في الفحص الأخير، فهو غير مفعّل افتراضيًا.
- يقرأ كل إعلان من صفحته نفسها: السعر، والموديل، والممشى، واللون، والموقع، وتاريخ النشر، والبائع، والهاتف إن ظهر.
- يحفظ الإعلان مرة واحدة، ويحدّث سعره إن تغيّر، ويربط الإعلان بأكثر من طلب بحث. لا تُدمج إعلانات منصات مختلفة اعتمادًا على تشابه الأرقام.
- **تقييم السعر العادل:** يقارن كل سعر بالمتوقع لنفس الطراز والسنة والممشى من إعلانات رصدها خلال 60 يومًا.
- **هبوط السعر:** يظهر ضمن جولتي البحث اليوميتين، دون فحوص أو تنبيهات إضافية.
- **مؤشر استعجال البائع:** يحسبه من مدة العرض، وعدد مرات تخفيض السعر، وعبارات مثل «مستعجل» و«مسافر».
- **المقارنة:** حتى 3 سيارات جنبًا إلى جنب، مع توصية بالأفضل وأسبابها.
- **التقرير المجمع:** الساعة 10 صباحًا و8 مساءً، يعرض الجديد وتخفيضات الأسعار. أول جولة مجدولة تعرض نتائج الشهر.

## المواعيد (بتوقيت الإمارات)

| الوقت | ما يحدث |
|---|---|
| 10:00 ص | بحث وتقرير مجمع وPDF، يصلك على كل قناة مفعّلة، دائمًا |
| 8:00 م | بحث وتقرير مجمع وPDF، يصلك على كل قناة مفعّلة، دائمًا |
| «ابحث الآن» | بحث فوري من اللوحة، دون إشعار |

قد يؤخر GitHub المواعيد المجدولة من 5 إلى 15 دقيقة في أوقات الضغط.

## الإعداد (مرة واحدة)

### 1. تشغيل الصفحة
**Settings ← Pages ← Build and deployment:** اختر Source = `Deploy from a branch`، ثم Branch = `main` والمجلد `/ (root)`، ثم Save.

### 2. كلمة سر البيانات (إلزامي)
البيانات في هذا المستودع العام مشفّرة. اختر كلمة سر قوية، ثم أضفها في:
**Settings ← Secrets and variables ← Actions ← New repository secret**
- الاسم: `RADAR_KEY`
- القيمة: كلمة السر

استخدم كلمة السر نفسها عند فتح اللوحة.

### 3. مفتاح GitHub للوحة (للتعديل وزر «ابحث الآن»)
1. افتح https://github.com/settings/personal-access-tokens/new
2. في **Repository access** اختر `Only select repositories` ثم `uae-car-radar`.
3. في **Permissions ← Repository permissions:**
   - **Contents:** Read and write
   - **Actions:** Read and write
4. اضغط **Generate token**، ثم الصق المفتاح في اللوحة مرة واحدة. يُحفظ مشفرًا على جهازك عند تفعيل «تذكّر هذا الجهاز».

### 4. الإشعارات (اختر ما تريد)
كل قناة تُفعَّل عند إضافة أسرارها في **Secrets and variables ← Actions**.

**تيليجرام (يرسل الملخص وملف PDF):**
1. في تيليجرام افتح `@BotFather`، وأرسل `/newbot`، واتبع الخطوات. ستحصل على مفتاح البوت.
2. افتح البوت الجديد واضغط Start.
3. افتح `@userinfobot` وانسخ رقم `Id`.
4. أضف السرين: `TELEGRAM_BOT_TOKEN` (مفتاح البوت) و`TELEGRAM_CHAT_ID` (الرقم).

**واتساب عبر CallMeBot (نص فقط):**
1. اتبع التعليمات في https://www.callmebot.com/blog/free-api-whatsapp-messages/ لتحصل على apikey.
2. أضف السرين: `CALLMEBOT_PHONE` (رقمك بصيغة +9715xxxxxxxx) و`CALLMEBOT_APIKEY`.

**واتساب: الخطوة المؤجلة (أكتوبر 2026)**
تيليجرام والبريد مفعّلان ومُختبران. واتساب مؤجل لأن CallMeBot ممتلئ ويخفي رقمه (`+34*********`). الخيارات:
1. **CallMeBot** (مجاني): عندما يظهر رقمه في صفحته، أرسل له `I allow callmebot to send me messages` وأضف السرين أعلاه.
2. **Green-API** (مجاني، 3 محادثات): غير رسمي ويرتبط بواتساب كجهاز مرتبط يستطيع رؤية الرسائل الواردة، لذلك على **شريحة ثانية فقط**، لا على الرقم الشخصي.
3. **واتساب الرسمي من Meta (Cloud API)**: بلا خطر حظر أو خصوصية، حوالي 0.016 دولار للرسالة في الإمارات (أقل من دولار شهريًا). يحتاج قالب رسالة معتمدًا وإضافة دعمه في `engine/notify.py`.

**البريد عبر Gmail (يرسل الملخص وملف PDF):**
1. فعّل التحقق بخطوتين في حساب Google، ثم أنشئ «كلمة مرور تطبيق» من https://myaccount.google.com/apppasswords
2. أضف السرين: `SMTP_USER` (بريدك) و`SMTP_PASSWORD` (كلمة مرور التطبيق).
3. اختياريًا أضف `MAIL_TO` إن أردت الإرسال إلى بريد آخر.

بعد إضافة الأسرار اضغط في اللوحة **الإعدادات ← إرسال إشعار تجريبي**.

### 5. أول استخدام
افتح الرابط، واكتب كلمة السر ومفتاح GitHub. أول مرة تنشئ اللوحة ملف البيانات. بعدها أضف طلب بحث واضغط «ابحث الآن».

## الخصوصية

- المستودع عام، لكن كل بياناتك محفوظة مشفّرة بـ AES-256 بكلمة سرك: الطلبات، والإعلانات، والمتابعة، والتقارير، وتقدّم البحث المباشر، وإحصاءات كل جولة، ونتائج «فحص المنصات».
- لا يوجد أي ملف بيانات غير مشفّر في المستودع. رسائل الحفظ عامة («dashboard: sync» و«radar: update data») ولا تكشف ما تغيّر.
- سجلات GitHub Actions العامة لا تطبع إلا أعدادًا، دون شروط بحث أو إعلانات أو أرقام هواتف.
- لا يُحفظ أي مفتاح أو كلمة سر داخل الكود.
- **ما يبقى ظاهرًا بطبيعة المستودع العام:** الكود، وأوقات تشغيل المهام، وأوقات الحفظ، وأحجام الملفات المشفّرة. لإخفاء هذه أيضًا يجب جعل المستودع خاصًا، وهذا يحتاج GitHub Pro لاستضافة الصفحة من مستودع خاص، أو نقل الاستضافة إلى خدمة تدعم المستودعات الخاصة مجانًا.

## حدود معروفة

- **دوبيزل يحجب خوادم GitHub** (صفحة «Pardon Our Interruption»). الرادار لا يتحايل على هذه الحماية؛ يحاول إيجاد إعلاناته عبر محرك بحث، وهذا لا ينجح دائمًا. كثير من معارض دوبيزل تنشر نفس السيارات على DubiCars ويلا موتور، والرادار يجمع النسخ المكررة.
- بعض المنصات (DubiCars، OneClickDrive) قد ترفض الطلبات أحيانًا إذا تكررت خلال دقائق؛ في المواعيد العادية يعمل البحث طبيعيًا.

- الرادار يقرأ الصفحات العامة كما يقرؤها المتصفح، ولا يتحايل على أي حماية. المنصة التي تحجب خوادم GitHub يبحث عن إعلاناتها عبر محرك بحث بديل، وتظهر إعلاناتها تحت «تحتاج تأكيدًا» إذا تعذّر فتحها.
- بعض المنصات لا تعرض تاريخ النشر ولا رقم الهاتف نصًا، فيُكتب مصدر التاريخ بجانبه، ويظهر الهاتف «في صفحة الإعلان».
- «فحص المنصات» في الإعدادات يوضح ما تعرضه كل منصة الآن.

## للمطورين

```
python -m unittest discover engine/tests        # اختبارات بدون إنترنت
RADAR_KEY=... python engine/radar.py run --mode manual
python engine/radar.py diagnose --make Toyota --model Yaris
```

## دقة البحث وحماية البيانات

- السعر حد أقصى شامل، وسنوات الموديل تشمل البداية والنهاية. يدعم «تيوتا» و«تويوتا» ويمنع حفظ أسماء عربية لا يستطيع تحويلها لمسار بحث؛ يمكن إدخال أسماء أخرى بالإنجليزية.
- ثلاث درجات للعروض:
  - **مطابقة:** كل الشروط ظاهرة في الإعلان، وتاريخ النشر ضمن الشهر.
  - **مطابقة بلا تاريخ نشر:** كل الشروط مطابقة، لكن المنصة لا تنشر تاريخ النشر (DubiCars وOneClickDrive)، أو تعرض تاريخ تحديث أو صور أو فحص ضمن الشهر. تُعرض مع النتائج بشارة واضحة، ومصدر التاريخ مكتوب بجانبها.
  - **تحتاج تأكيدًا:** شرط من الشروط غير ظاهر في الإعلان.
- الإعلانات الأقدم من الشهر تبقى في البيانات للمتابعة ولا تدخل التقرير.
- السعر يُقبل من صفحة الإعلان نفسها فقط. سعر بطاقة النتائج لا يثبت سعر البيع النقدي، ولا يكفي تجاوز 5,000 درهم لاستبعاد الأقساط. تُخفى أسعار البطاقات القديمة إلى حين إعادة التحقق، وتُستبعد من تقييم السوق.
- أسعار العملات الأخرى لا تُعامل كدرهم. السعر النقدي الصريح ورسومه الظاهرة يسبقان المبلغ المحول في البيانات المنظمة؛ البيانات المتعارضة أو الناقصة تحتاج مراجعة المصدر.
- الجولة المجدولة تُتجاوز عند وصول إشارة نشاط موثوقة خلال آخر 3 دقائق من اللوحة. الإشارة مشفّرة في `data/activity.enc` على فرع `radar-live`، ولا تحتوي إلا وقت النشاط. المراجعة الأسبوعية مستقلة عن هذا الشرط.
- الإشعارات: التقرير يُرسل إلى **كل** قناة مفعّلة. البريد وتيليجرام يحملان النص الكامل وملف PDF، وواتساب رسالة مختصرة برابط اللوحة (CallMeBot يقبل الرسائل القصيرة فقط). كل قناة تُعاد محاولتها مرة إذا فشلت، وأي قناة لم يصل عبرها التقرير تظهر في لوحة «التنبيهات» أعلى الصفحة.
- الأخطاء لا توقف الجدولة: فشل اختبارات الجودة أو فحص مولّد التقارير يُسجَّل تنبيهًا وتستمر الجولة، وأي خطأ برمجي يُحفظ كجولة «لم تكتمل» مع نوع الخطأ ومكانه. مهام GitHub التي تفشل قبل تسجيل أي شيء تظهر أيضًا في اللوحة مع اسم الخطوة.
- نفس السيارة على أكثر من منصة (رقم شاصي كامل صالح ومتطابق، مع نطاق طلبات ودرجات مطابقة متكافئة) تظهر مرة واحدة بأقل سعر، وتحتها النسخ الأخرى بأسعارها وروابطها.
- تذكّر الجهاز يستخدم مفتاح AES-GCM غير قابل للتصدير داخل IndexedDB مع بيانات دخول مشفرة، وترحيل الحفظ القديم تلقائيًا. يظل الجهاز والبرامج التي تعمل على نفس أصل الموقع موضع ثقة؛ «نسيان الجهاز» يمسح الحفظ المحلي.
- نتائج «فحص المنصات» محفوظة مشفّرة. تاريخ git القديم قد يحتوي تشخيصات أو إشارات نشاط سابقة؛ التحديث لا يمحو تاريخ المستودع.
- عند تعارض الحفظ من جهازين تُرفض الكتابة القديمة ويُطلب التحديث، بدل استبدال أحدث تعديل.
- حدود التغطية مستمرة: حجب المنصات وحدود الصفحات يعنيان أن التقرير ليس مسحًا شاملاً للسوق. عدم العثور على نتائج لا يثبت غياب العروض.

## هوية الواجهة والأسعار

- الهوية: كحلي `#0B1732`، تركواز `#36D5C1`، أزرق `#3D70F4`، وخلفية فاتحة `#F3F6FB`؛ الخط Cairo للعربية وInter للإنجليزية والأرقام.
- الشعار المتجهي في `assets/logo.svg`، والعلامة المختصرة والأيقونة في `assets/logo-mark.svg`.
- لا تظهر إعلانات بلا سعر في الإعلانات أو المقارنة أو التصدير أو تقارير البحث الجديدة. التقارير القديمة تحتفظ بلقطة نتائجها السابقة.
- محلل الأسعار يقرأ عروض الإعلان وبياناته الوصفية وسعره المعلن بالدرهم؛ لا يحوّل أسعار الدولار تخمينيًا، ولا يستخدم أرقام التمويل أو توصيات سيارات أخرى كسعر للإعلان.
- تعارض سعرين صريحين بالدرهم يستبعد الإعلان حتى التحقق، ولا يُختار أحدهما عشوائيًا. يعاد فحص السجلات القديمة والناقصة لتصحيح السعر دون انتظار فترة الفحص المعتادة.


## تحديث دورة البحث والمتابعة

- البحث اليدوي يحدّث الإعلانات والسجل فقط، ولا ينشئ PDF ولا يرسل ملخص بحث خارجيًا.
- تقارير PDF عند 10 صباحًا و8 مساءً بتوقيت الإمارات للطلبات المجدولة وعند غياب المستخدم.
- الاثنين 8 صباحًا بتوقيت الإمارات: مراجعة أسبوعية للإعلانات الناتجة عن الطلبات المحفوظة النشطة، حتى 100 سيارة في الجولة. يظهر العدد المؤجل في السجل، وتُقدّم الأقل مراجعة في الجولة التالية. لا PDF للمراجعة الأسبوعية.
- تغيّر السعر أو البيانات وحالات البيع والحذف والحجز تسجّل في التحديثات. خطأ الاتصال أو الحجب لا يثبت البيع. الإشعارات تخرج عبر قناة المستخدم المفعّلة عند اكتشاف التغيّر، وليست مراقبة لحظية للمنصات.
- اترك الماركة والطراز فارغين لبحث عام؛ دليل مرجان مبني على أقسام السيارات الفعلية في `engine/mourjan_catalog.json`. هوية الإعلان مقيدة بهذه الأقسام حتى لا تدخل إعلانات وظائف أو عقارات. يتم حل أرقام الطراز من نموذج كل ماركة بدل قصرها على تويوتا.
- `data/search-progress.json` على فرع `radar-live` المنفصل يحمل تقدّم البحث المباشر مشفّرًا بنفس كلمة السر، ولا ينشئ نشره عملية Pages جديدة.

- مراجعة 2026-10-19: دمج التكرارات يحتاج VIN صالحًا ومتطابقًا ونطاق طلبات مكافئًا؛ يُعاد حسابه في المراجعة الأسبوعية بعد السعر أو الحذف أو الحجز. تحذيرات الجودة تدخل ملف PDF، وإخفاق إشعارات المراجعة الأسبوعية يظهر في اللوحة.

## Platform health monitoring

Each search stores encrypted health counters for attempted platforms: reachable/blocked pages, discovered ad links, opened/read detail pages and confirmed prices. An alert requires a successful baseline for the same request criteria followed by two consecutive rounds with zero extracted links, or two successful detail-reading rounds with zero confirmed prices after prior price success. Filtered match counts do not trigger parser alarms; network failures do not count as successful price reads, and unattempted platforms do not advance counters. Search changes get a separate baseline (up to 12 scopes/platform). Alerts appear on the dashboard and in scheduled summaries; recovery appears in Settings → صحة المنصات. Health never marks a vehicle sold. Counters are evidence of extraction, not a guarantee of full platform coverage.

Real sanitized OpenSooq and Mourjan snapshots live in engine/tests/fixtures. Offline tests complement live counters; old snapshots cannot themselves detect tomorrow's markup changes.

## Dubizzle email findings

Official references:
- https://support.dubizzle.com/hc/en-us/articles/14780756686866-Can-I-save-my-search-preferences-for-future-use
- https://support.dubizzle.com/hc/en-us/articles/14778324154642-How-to-manage-Email-and-Push-notifications-on-the-dubizzle-app

Saved searches and email recommendations exist, but recommendations are not guaranteed to satisfy a saved request. Receiving date is not posting date. Email may omit phone/VIN and may carry tracking links or multiple unrelated prices. The app does not currently read a mailbox. A ChatGPT Gmail connection is not available to GitHub Actions. Continuous mailbox access would need a separate authorized integration (Google documents server-side OAuth/offline access at https://developers.google.com/workspace/gmail/api/auth/web-server). No mailbox credentials, raw messages, or tracking tokens are stored in this public repository. No paid email service was added. Until an actual saved-search message and mailbox authorization are validated, email recommendations are not injected as verified car listings. Settings contains the official saved-search instructions and explicitly shows that automatic import is inactive.

## Fresh purchase opportunities

A separate الفرص workspace and an in-page notification dialog shortlist fresh purchase leads. Hourly cron `17 * * * *` runs `run --mode opportunity`: up to 20 new ads, no due saved-ad rechecks, no PDF, active requests with an explicit make and model only. Users can pause from الفرص; manual/scheduled rounds also refresh the shortlist. GitHub cron may be delayed or skipped: this is not instant monitoring.

Eligibility: own-page AED price, available and request-verified, published within the last two calendar days in UAE time and checked within six hours. Requires at least eight comparable ads for that request. At least 10% below the estimated asking-price comparison and at/below its lower quartile qualifies for اتصل اليوم if phone/mileage are available; 35%+ below estimate or missing phone/mileage goes to تحقق أولًا. Discounts from 4% below estimate go to راقب السعر. The comparison is observed asking prices, not a valuation, mechanical inspection, or guarantee of a bargain. Broad all-model requests cannot supply reliable comparisons and are excluded.

Sold/reserved/unavailable, dismissed/purchased, unreachable, observed price changes and observed non-availability edits are excluded from the opportunity shortlist; lifecycle history remains separate. Editing is not evidence that the seller is a dealer. Price history is retained. Strong opportunities get one in-page event per known identity (valid published VIN or listing ID); successful external hourly notification is remembered to avoid repeats. Failed/off channels may retry while the opportunity remains eligible. Manual searches keep their existing no-external-summary/no-PDF behavior. No paid APIs or services added.
