# Supabase cloud sync (small test)

The free Supabase project is the durable store for the current small test. The
Render service remains the only holder of the Supabase service-role key; iOS
and macOS communicate only with the existing RHYTHMOS HTTPS service.

## Schema

Run `db/supabase/001_rhythmos_cloud_sync.sql` once in the project's SQL Editor.
It creates `public.rhythmos_sync_documents`, enables RLS, and grants no
client-facing access. The service-role key bypasses RLS only inside Render.

## Render environment

Set these values only in Render's environment configuration; never put them in
the iOS project, macOS application bundle, repository, logs, or chat:

| Variable | Value |
| --- | --- |
| `SUPABASE_URL` | Project Settings → API → Project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Project Settings → API → service-role key |
| `CLOUD_SYNC_SOURCE_DEVICE` | `render-polar-service` |

The existing `MOBILE_SYNC_API_TOKEN` continues to protect client-to-Render
requests. It is not a Supabase credential.

## Synchronization model

1. Polar data and approved iOS entries reach Render over HTTPS.
2. Render writes a versioned daily snapshot and history documents to Supabase.
3. iOS reads those projections through Render, never directly from Supabase.
4. macOS can securely publish or pull the same document types through
   `/v1/cloud/documents/<type>/<key>` using the existing RHYTHMOS token.

This test-stage account is scoped server-side by `POLAR_MEMBER_ID`. A later
multi-user release must replace that with an authenticated RHYTHMOS account
identity and per-user authorization.

## macOS publisher

After Render is configured, add the following only to the local `.env` file
(never the repository):

```dotenv
RHYTHMOS_SYNC_SERVICE_URL=https://rhythmos-bk8d.onrender.com
MOBILE_SYNC_API_TOKEN=the_existing_mobile_token
```

Run `./.venv/bin/python scripts/publish_cloud_projections.py` after a local
sync to publish the mobile-safe daily snapshots plus 14-day recovery/training
history. It publishes through Render rather than directly to Supabase, and it
does nothing unless both settings are present.
