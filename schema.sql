-- ==============================================================================
-- ClientPulse - Supabase PostgreSQL Database Schema
-- ==============================================================================
-- Run this script in your Supabase SQL Editor (Dashboard -> SQL Editor -> New Query)

-- 1. Create Clients Table
CREATE TABLE IF NOT EXISTS public.clients (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL,
    email TEXT,
    industry TEXT,
    website TEXT,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- 2. Create Reports Table
CREATE TABLE IF NOT EXISTS public.reports (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    client_id TEXT NOT NULL REFERENCES public.clients(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    impressions BIGINT NOT NULL DEFAULT 0,
    clicks BIGINT NOT NULL DEFAULT 0,
    leads BIGINT NOT NULL DEFAULT 0,
    spend NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    ctr NUMERIC(6, 2) NOT NULL DEFAULT 0.00,
    cpl NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    conversion_rate NUMERIC(6, 2) NOT NULL DEFAULT 0.00,
    prev_impressions BIGINT NOT NULL DEFAULT 0,
    prev_clicks BIGINT NOT NULL DEFAULT 0,
    prev_leads BIGINT NOT NULL DEFAULT 0,
    prev_spend NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    summary TEXT,
    recommendations TEXT,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published')),
    share_token TEXT UNIQUE NOT NULL DEFAULT md5(random()::text || clock_timestamp()::text),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- 3. Create Activity Logs Table
CREATE TABLE IF NOT EXISTS public.activity_logs (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    details TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- 4. Create Indexes for High Performance
CREATE INDEX IF NOT EXISTS idx_clients_status ON public.clients(status);
CREATE INDEX IF NOT EXISTS idx_reports_client_id ON public.reports(client_id);
CREATE INDEX IF NOT EXISTS idx_reports_status ON public.reports(status);
CREATE INDEX IF NOT EXISTS idx_reports_share_token ON public.reports(share_token);
CREATE INDEX IF NOT EXISTS idx_reports_created_at ON public.reports(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_logs_created_at ON public.activity_logs(created_at DESC);

-- 5. Row-Level Security (RLS) Setup
ALTER TABLE public.clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.activity_logs ENABLE ROW LEVEL SECURITY;

-- Policies are dropped first so this script can be re-run safely.
-- The ClientPulse server should use the service_role key (server-side only; it bypasses RLS).
-- The anon role can only read published reports; it cannot read drafts or clients, or write anything.
DROP POLICY IF EXISTS "Public read for published reports" ON public.reports;
DROP POLICY IF EXISTS "Full access for authenticated users to clients" ON public.clients;
DROP POLICY IF EXISTS "Full access for authenticated users to reports" ON public.reports;
DROP POLICY IF EXISTS "Full access for authenticated users to activity_logs" ON public.activity_logs;

-- Allow public read of published reports via share_token
CREATE POLICY "Public read for published reports"
    ON public.reports
    FOR SELECT
    TO anon, authenticated
    USING (status = 'published');

-- Allow full access for signed-in agency users (previously this applied to every role, including anon)
CREATE POLICY "Full access for authenticated users to clients"
    ON public.clients
    FOR ALL
    TO authenticated
    USING (true)
    WITH CHECK (true);

CREATE POLICY "Full access for authenticated users to reports"
    ON public.reports
    FOR ALL
    TO authenticated
    USING (true)
    WITH CHECK (true);

CREATE POLICY "Full access for authenticated users to activity_logs"
    ON public.activity_logs
    FOR ALL
    TO authenticated
    USING (true)
    WITH CHECK (true);
