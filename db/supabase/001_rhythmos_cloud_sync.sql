-- RHYTHMOS cross-device synchronization, test-stage schema.
--
-- The Render service is the only application credential holder. Mobile and
-- desktop clients authenticate to that service; they never receive a Supabase
-- service-role key. RLS deliberately has no client-facing policies, so the
-- generated Data API cannot read health documents with anon/authenticated keys.

create table if not exists public.rhythmos_sync_documents (
    account_id text not null check (char_length(account_id) between 1 and 160),
    document_type text not null check (
        document_type in ('daily_snapshot', 'recovery_history', 'training_history')
    ),
    document_key text not null check (char_length(document_key) between 1 and 160),
    revision bigint not null default 1 check (revision > 0),
    payload jsonb not null,
    payload_sha256 text not null check (payload_sha256 ~ '^[a-f0-9]{64}$'),
    source_device text not null check (char_length(source_device) between 1 and 160),
    updated_at timestamptz not null default now(),
    primary key (account_id, document_type, document_key)
);

alter table public.rhythmos_sync_documents enable row level security;
revoke all on table public.rhythmos_sync_documents from anon, authenticated;

create index if not exists rhythmos_sync_documents_account_updated_idx
    on public.rhythmos_sync_documents (account_id, updated_at desc);

comment on table public.rhythmos_sync_documents is
    'Private, versioned RHYTHMOS health projections for account-scoped device synchronization.';
