# syntax=docker/dockerfile:1

# Prebuilt Eagle Eye Information Division release.
# The bundle is produced and tested before deployment so the production server
# does not need to download or compile npm dependencies.
FROM node:24-slim AS runner

WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

ADD deployment/eagle-eye-app.tar.gz ./

RUN mkdir -p /data && chown -R node:node /app /data

EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD ["node", "-e", "fetch('http://127.0.0.1:3000').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]
CMD ["sh", "-c", "chown node:node /data && exec setpriv --reuid=node --regid=node --init-groups node server.js"]
