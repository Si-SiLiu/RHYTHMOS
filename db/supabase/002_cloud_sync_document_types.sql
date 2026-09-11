-- Bring already-created small-test projects in line with the application
-- contract. Run after 001 in Supabase SQL Editor. This migration is additive:
-- it preserves every existing document and never prunes historical snapshots.

alter table public.rhythmos_sync_documents
    drop constraint if exists rhythmos_sync_documents_document_type_check;

alter table public.rhythmos_sync_documents
    add constraint rhythmos_sync_documents_document_type_check check (
        document_type in (
            'daily_snapshot',
            'recovery_history',
            'training_history',
            'nutrition_history',
            'personal_history',
            'mobile_change',
            'mobile_request',
            'mobile_session',
            'mobile_account',
            'mobile_credential'
        )
    );

comment on table public.rhythmos_sync_documents is
    'Private, versioned RHYTHMOS health projections. Daily snapshots are durable archive records; 28-day iPhone histories are separate documents and are not a retention policy.';
