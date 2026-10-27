# تثبيت المحرك باستخدام صورة GHCR عامة على Coolify

## 1) GitHub — نشر الصورة أول مرة

المستودع العام: https://github.com/hussamalbarouki/facebook-intelligence-engine

1. افتح تبويب **Actions** وشاهد تشغيل Workflow باسم `Test and publish GHCR image` بعد دفع ملفات المشروع إلى `main`.
2. انتظر نجاح الاختبارات وبناء Docker ونشر الصورة. نجاح بناء Docker لا يثبت نجاح استخراج فيسبوك.
3. افتح **Packages** في GitHub، ثم `facebook-intelligence-engine` → `Package settings` → `Change visibility` → **Public** إذا كان خاصًا. المستودع العام لا يعني بالضرورة أن حزمة GHCR عامة.
4. الصورة العامة المراد سحبها:

```
ghcr.io/hussamalbarouki/facebook-intelligence-engine:latest
```

## 2) Coolify — تثبيت مرة واحدة

1. ادخل Project → Environment → **+ New** → **Docker Image** (وليس Git Repository).
2. Image Name = `ghcr.io/hussamalbarouki/facebook-intelligence-engine:latest`، واضغط Save.
3. افتح **General** واجعل **Ports Exposes = 8000**.
4. أضف Domain باسم HTTPS مثل `https://fb-api.example.com` بعد ضبط DNS نحو VPS.
5. من **Environment Variables** أضف متغير Runtime سري باسم **`API_KEY`**، وقيمته سلسلة عشوائية لا تقل عن 32 محرفًا. لا تضفه على GitHub.
6. من **Persistent Storage** أضف **Volume Mount** مع **Destination Path = `/data`**. لا تكمل دون هذه الخطوة لأنها تحفظ التشفير، Cookies، قاعدة المهام.
7. اضغط **Deploy** وتحقق من Logs ومن `https://fb-api.example.com/healthz`.
8. افتح `/docs` واستعمل زر Authorize في Swagger لتمرير مفتاح `X-API-Key`؛ كل عمليات الإدارة والبيانات محمية.

ملاحظة: لا تدخل Cookies داخل Coolify ولا GitHub؛ أضفها من لوحة PHP لاحقًا عبر `PUT /v1/facebook/cookies`، ويمكن تحديثها دون Restart.

## 3) إعادة النشر والتحديث

GitHub Actions يبني الصورة بعد كل Push. تطبيق Coolify من نوع Docker Image **لا يعمل معه Git Auto-deploy تلقائيًا**؛ أعد Redeploy يدويًا لتجربة التحديث، أو اضبط GitHub Secrets اختياريًا `COOLIFY_DEPLOY_WEBHOOK` و`COOLIFY_TOKEN` لتشغيل Redeploy بعد نجاح النشر.

إذا مسحت VPS بالكامل، أعد Coolify/الدومين/المفتاح/Volume وعرّف Cookies مجددًا. GitHub وحده يعيد **الكود** وليس حالة التشغيل أو جلسة فيسبوك. راجع [Recovery](RECOVERY-AR.md).

### فحوصات بسيطة

- `GET /healthz`: يعمل دون مفتاح ويظهر إصدار المحرك.
- `GET /v1/status` مع `X-API-Key`: يظهر حالة Cookies والإعدادات.
- `GET /v1/capabilities`: ما تدعمه النسخة.
- أرسل مهمة على منشور عام مسموح لك الوصول إليه ثم راقب `GET /v1/jobs/{id}`.

**مراجع:** https://coolify.io/docs/applications/deployments/docker-image و https://coolify.io/docs/applications/configuration/environment-variables و https://coolify.io/docs/applications/configuration/persistent-storage