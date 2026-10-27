# REST API — المرجع الكامل للإدارة والتكامل

**Base URL:** `https://fb-api.example.com`، جميع المسارات `/v1/*` محمية بـ`X-API-Key: YOUR_API_KEY` ويجب استدعاؤها من **خادم PHP** لا من JavaScript داخل المتصفح.

افتح `https://YOUR_DOMAIN/docs` للتوثيق التفاعلي التلقائي و`/openapi.json` لمخطط OpenAPI.

## الحالة العامة

| Method | Endpoint | النتيجة |
|---|---|---|
| GET | `/healthz` | حالة العملية، بلا مفتاح |
| GET | `/v1/status` | الحالة، إعدادات المحرك، حالة Cookies، إحصاءات المهام |
| GET | `/v1/capabilities` | الميزات والقيود والتوافق |
| GET | `/v1/metrics` | إحصاءات الحالات وطلبات آخر 24 ساعة |
| GET | `/v1/events?limit=30` | سجل عمليات دون أي قيم سرية |

## إدارة Cookies (من لوحة PHP)

**إضافة/تبديل:**

```http
PUT /v1/facebook/cookies
X-API-Key: YOUR_API_KEY
Content-Type: application/json
```

```json
{"cookies":{"c_user":"VALUE","xs":"VALUE","datr":"OPTIONAL"}}
```

يمكن إرسال قائمة JSON مُصدّرة من المتصفح بدل قاموس. يشترط `c_user` و`xs`، ولا تُقبل Cookies لنطاقات غير فيسبوك. تحفَظ بشكل مشفر في SQLite ضمن `/data` بواسطة مفتاح محلي خاص `/data/cookie-encryption.key`. لا تعيد الخدمة القيم السرية في أي GET.

**فحص تهيئتها دون إثبات صلاحية الجلسة:** `GET /v1/facebook/cookies`.

**إزالتها:** `DELETE /v1/facebook/cookies`.

### لماذا نغيّر Cookies من PHP؟

موقع PHP يرسل `PUT` مع مفتاح المحرك عبر HTTPS، ويتم تحديث Cookies مباشرة للمهمة التالية. لا حاجة لتعديل صورة Docker أو GitHub، ولا حاجة إلى Restart. يجب حماية واجهة إدارة PHP وتفعيل CSRF وHTTPS وحصر هذا الإجراء بالمشرف.

## التحكم بالإعدادات

`GET /v1/settings`، `PATCH /v1/settings`.

```json
{"default_comments_limit":100,"default_reactors_limit":100,"max_comments_limit":1000,"max_reactors_limit":1000,"retention_days":7,"request_cooldown_seconds":5,"jobs_enabled":true}
```

هذه الحقول قابلة للتعديل دون إعادة التشغيل؛ لا تتجاوز حدود 1000 لكل نوع. `jobs_enabled=false` يوقف قبول المهام الجديدة ويوقف سحب المهام من الطابور، لكنه لا يوقف اتصالًا جارياً فورًا.

## تنفيذ مهمة

`POST /v1/jobs`:

```json
{"url":"https://www.facebook.com/USER/posts/POST_ID","comments_limit":50,"reactors_limit":50,"client_job_id":"php-task-101"}
```

- كل الحدود اختيارية وتستخدم الإعدادات الافتراضية إن غابت.
- `client_job_id` معرّف فريد اختياري يمنع تكرار المهمة عند إعادة محاولة PHP بعد انقطاع اتصال.
- الاستجابة 202: `{"job_id":"...","status":"queued","reused":false}`.
- `POST /v1/jobs/{id}/retry`: إعادة مهمة فاشلة إلى الطابور.
- `POST /v1/jobs/{id}/cancel`: إلغاء مهمة في الطابور أو منع حفظ نتيجة مهمة جارية؛ الاتصال الجاري بفيسبوك قد يستمر حتى انتهائه.
- `GET /v1/jobs?status=failed&limit=30&offset=0`: قائمة المهام.
- `GET /v1/jobs/{id}`: حالة `queued/running/completed/failed/canceled` وبيانات الخطأ عند الفشل.

## النتائج

`GET /v1/jobs/{id}/result?comments_offset=0&reactors_offset=0&limit=100`.

النتائج تشمل بيانات المنشور، `comments[]` (اسم، نص، تاريخ، رابط، ردود)، `reactors[]` (اسم، نوع التفاعل، رابط الحساب)، `coverage` وإزاحات الصفحة التالية. **العدد الكلي للتفاعلات ليس مساويًا بالضرورة لعدد الأسماء المستخرجة. `coverage.complete` دائمًا false حاليًا لعدم وجود وسيلة تحقق من الشمول.**

## أخطاء HTTP

| الكود | المعنى |
|---|---|
| 401 | API key غير صحيح |
| 422 | رابط أو خيارات أو Cookies غير صالحة |
| 429 | طابور 20 عملية ممتلئ |
| 503 | تم تعطيل استقبال المهام |
| 404 | معرف المهمة غير موجود |
| 409 | حالة المهمة تمنع العملية، أو تكرار `client_job_id` بمحتوى مختلف |

أما `status=failed` مع `error=SCRAPE_FAILED` فتعني فشل الاستخراج، وقد يكون السبب تغير فيسبوك أو انتهاء Cookies أو صلاحيات المنشور. لا نفترض سببًا محددًا دون اختبار حي.

## PHP SDK

انقل `php/src/FacebookEngine.php` إلى موقعك (يفضل خارج public_html)، واضبط `FB_ENGINE_URL` و`FB_ENGINE_KEY` بشكل سري. استدعاءات الإدارة متوفرة: `setCookies`, `removeCookies`, `cookiesStatus`, `settings`, `updateSettings`, `status`, `capabilities`, `metrics`, `events`، بالإضافة إلى استدعاءات الوظائف: `startJob`, `listJobs`, `getJob`, `getResult`, `retryJob`, `cancelJob`.

**لا تنتظر اكتمال استخراج مئات التعليقات في نفس HTTP request بصفحة PHP**. خزّن `job_id` ثم تابع الحالة في طلبات أخرى أو Cron للاستضافة.