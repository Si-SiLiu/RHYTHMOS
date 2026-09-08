-- Add the private iOS-to-macOS mutation inbox.  Run once in the Supabase SQL
-- editor after 001_rhythmos_cloud_sync.sql; no client receives database keys.

alter table public.rhythmos_sync_documents
    drop constraint if exists rhythmos_sync_documents_document_type_check;

alter table public.rhythmos_sync_documents
    add constraint rhythmos_sync_documents_document_type_check check (
        document_type in ('daily_snapshot', 'recovery_history', 'training_history', 'mobile_change')
    );
