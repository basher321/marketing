-- PilotSonic database schema (structure only, no data), dumped 2026-10-21 from the local
-- PostgreSQL 16 database, which matches production (Neon). See SPEC-BE-106.
-- Needs PostgreSQL 13+ (generated column; 16+ recommended). Run as a role that may create extensions:
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS citext;

--
-- PostgreSQL database dump
--

\restrict CpXoa5aAAEuZm95L6zwCA3TpBzORvKAL39ZUf4Y71X5ZQ3ArsdNGfGlHyddbn3u

-- Dumped from database version 16.15
-- Dumped by pg_dump version 16.15

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA public;


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS 'standard public schema';


--
-- Name: actor_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.actor_type AS ENUM (
    'human',
    'ai',
    'system',
    'webhook'
);


--
-- Name: approval_decision; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.approval_decision AS ENUM (
    'pending',
    'approved',
    'rejected',
    'expired'
);


--
-- Name: approval_subject_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.approval_subject_type AS ENUM (
    'plan',
    'action',
    'content',
    'campaign',
    'reply',
    'pricing_change'
);


--
-- Name: campaign_objective; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.campaign_objective AS ENUM (
    'awareness',
    'traffic',
    'engagement',
    'conversions',
    'message_replies',
    'reach',
    'leads',
    'app_promotion'
);


--
-- Name: campaign_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.campaign_status AS ENUM (
    'draft',
    'scheduled',
    'running',
    'paused',
    'completed',
    'failed'
);


--
-- Name: channel_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.channel_type AS ENUM (
    'facebook',
    'instagram',
    'tiktok',
    'whatsapp',
    'messenger',
    'email',
    'sms',
    'web',
    'google',
    'linkedin',
    'x',
    'snapchat',
    'pinterest'
);


--
-- Name: content_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.content_status AS ENUM (
    'draft',
    'pending_approval',
    'approved',
    'rejected',
    'published',
    'archived'
);


--
-- Name: conversation_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.conversation_status AS ENUM (
    'open',
    'pending',
    'resolved',
    'archived'
);


--
-- Name: integration_provider; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.integration_provider AS ENUM (
    'facebook',
    'instagram',
    'tiktok',
    'meta_ads',
    'tiktok_ads',
    'google_ads',
    'whatsapp',
    'shopify',
    'woocommerce',
    'hubspot',
    'zoho',
    'salesforce',
    'smtp',
    'sendgrid',
    'linkedin_ads',
    'x_ads',
    'snapchat_ads',
    'pinterest_ads',
    'linkedin'
);


--
-- Name: integration_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.integration_status AS ENUM (
    'connected',
    'disconnected',
    'expired',
    'error'
);


--
-- Name: message_direction; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.message_direction AS ENUM (
    'inbound',
    'outbound'
);


--
-- Name: order_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.order_status AS ENUM (
    'pending',
    'confirmed',
    'processing',
    'shipped',
    'delivered',
    'cancelled',
    'refunded'
);


--
-- Name: plan_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.plan_status AS ENUM (
    'proposed',
    'partially_approved',
    'approved',
    'rejected',
    'executed',
    'failed',
    'draft',
    'submitted',
    'paused',
    'cancelled'
);


--
-- Name: post_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.post_status AS ENUM (
    'pending',
    'scheduled',
    'publishing',
    'published',
    'failed',
    'cancelled'
);


--
-- Name: pricing_rule_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.pricing_rule_type AS ENUM (
    'percent_discount',
    'fixed_discount',
    'tiered',
    'fixed_price'
);


--
-- Name: pricing_scope; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.pricing_scope AS ENUM (
    'sku',
    'category',
    'all',
    'tag'
);


--
-- Name: product_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.product_status AS ENUM (
    'draft',
    'active',
    'archived',
    'out_of_stock'
);


--
-- Name: role_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.role_type AS ENUM (
    'owner',
    'manager',
    'operator',
    'analyst',
    'viewer',
    'custom'
);


--
-- Name: run_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.run_status AS ENUM (
    'pending',
    'running',
    'succeeded',
    'failed',
    'cancelled',
    'retrying'
);


--
-- Name: sender_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.sender_type AS ENUM (
    'customer',
    'agent',
    'ai',
    'system'
);


--
-- Name: subscription_tier; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.subscription_tier AS ENUM (
    'free',
    'starter',
    'pro',
    'enterprise'
);


--
-- Name: tenant_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.tenant_status AS ENUM (
    'active',
    'suspended',
    'trial',
    'cancelled'
);


--
-- Name: user_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.user_status AS ENUM (
    'active',
    'invited',
    'disabled',
    'locked'
);


--
-- Name: workflow_action_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.workflow_action_type AS ENUM (
    'generate_content',
    'schedule_post',
    'launch_ad',
    'adjust_budget',
    'send_message',
    'create_task',
    'notify_owner',
    'call_webhook',
    'update_product',
    'adjust_pricing'
);


--
-- Name: workflow_trigger_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.workflow_trigger_type AS ENUM (
    'product_created',
    'product_updated',
    'inventory_low',
    'order_placed',
    'order_fulfilled',
    'order_refunded',
    'order_abandoned_cart',
    'message_received',
    'schedule_cron',
    'ad_threshold_crossed',
    'content_published',
    'manual_owner_command'
);


--
-- Name: update_updated_at_column(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: abandoned_carts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.abandoned_carts (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    customer_id uuid,
    session_id character varying(255),
    cart_items jsonb DEFAULT '[]'::jsonb NOT NULL,
    subtotal_cents bigint DEFAULT 0 NOT NULL,
    email public.citext,
    phone character varying(50),
    recovered_order_id uuid,
    reminder_sent_count integer DEFAULT 0 NOT NULL,
    last_reminder_at timestamp with time zone,
    abandoned_at timestamp with time zone DEFAULT now() NOT NULL,
    recovered_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: action_executions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.action_executions (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    workflow_run_id uuid NOT NULL,
    action_index integer NOT NULL,
    action_type public.workflow_action_type NOT NULL,
    input jsonb DEFAULT '{}'::jsonb NOT NULL,
    output jsonb,
    status public.run_status DEFAULT 'pending'::public.run_status NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    max_attempts integer DEFAULT 6 NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    next_retry_at timestamp with time zone,
    error_message text,
    idempotency_key character varying(255),
    correlation_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: ad_groups; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ad_groups (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    audience_id uuid,
    targeting jsonb DEFAULT '{}'::jsonb NOT NULL,
    budget_cents bigint,
    bid_strategy character varying(50),
    status public.campaign_status DEFAULT 'draft'::public.campaign_status NOT NULL,
    external_id character varying(255),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: ads; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ads (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    ad_group_id uuid NOT NULL,
    content_asset_id uuid,
    name character varying(255) NOT NULL,
    status public.campaign_status DEFAULT 'draft'::public.campaign_status NOT NULL,
    external_ad_id character varying(255),
    external_url text,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: ai_campaign_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_campaign_runs (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    created_by uuid,
    prompt text NOT NULL,
    request jsonb NOT NULL,
    status character varying(30) NOT NULL,
    stage character varying(30),
    stages jsonb DEFAULT '[]'::jsonb NOT NULL,
    campaign_ids uuid[] DEFAULT '{}'::uuid[] NOT NULL,
    cost_cents integer DEFAULT 0 NOT NULL,
    error text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: analytics_daily_rollups; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.analytics_daily_rollups (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    day date NOT NULL,
    entity_type character varying(50) NOT NULL,
    entity_id uuid,
    channel public.channel_type,
    metric character varying(100) NOT NULL,
    value numeric(20,4) NOT NULL,
    dimensions jsonb DEFAULT '{}'::jsonb NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: analytics_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.analytics_events (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    event_time timestamp with time zone DEFAULT now() NOT NULL,
    event_type character varying(100) NOT NULL,
    entity_type character varying(50) NOT NULL,
    entity_id uuid NOT NULL,
    metric character varying(100) NOT NULL,
    value numeric(20,4) NOT NULL,
    dimensions jsonb DEFAULT '{}'::jsonb NOT NULL,
    correlation_id uuid,
    source character varying(100),
    created_at timestamp with time zone DEFAULT now() NOT NULL
)
PARTITION BY RANGE (event_time);


--
-- Name: analytics_events_default; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.analytics_events_default (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    event_time timestamp with time zone DEFAULT now() NOT NULL,
    event_type character varying(100) NOT NULL,
    entity_type character varying(50) NOT NULL,
    entity_id uuid NOT NULL,
    metric character varying(100) NOT NULL,
    value numeric(20,4) NOT NULL,
    dimensions jsonb DEFAULT '{}'::jsonb NOT NULL,
    correlation_id uuid,
    source character varying(100),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: api_keys; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.api_keys (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    user_id uuid,
    name character varying(255) NOT NULL,
    key_prefix character varying(20) NOT NULL,
    key_hash character varying(255) NOT NULL,
    scopes text[] DEFAULT '{}'::text[] NOT NULL,
    last_used_at timestamp with time zone,
    expires_at timestamp with time zone,
    revoked_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: approval_queue; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.approval_queue (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    subject_type public.approval_subject_type NOT NULL,
    subject_id uuid NOT NULL,
    title character varying(500) NOT NULL,
    summary text,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    requested_by_type public.actor_type NOT NULL,
    requested_by uuid,
    requested_at timestamp with time zone DEFAULT now() NOT NULL,
    decision public.approval_decision DEFAULT 'pending'::public.approval_decision NOT NULL,
    decided_by uuid,
    decided_at timestamp with time zone,
    reason text,
    expires_at timestamp with time zone,
    correlation_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: audiences; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audiences (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    targeting jsonb DEFAULT '{}'::jsonb NOT NULL,
    channel public.channel_type,
    external_ids jsonb DEFAULT '{}'::jsonb NOT NULL,
    estimated_size integer,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: audit_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_log (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid,
    actor_type public.actor_type NOT NULL,
    actor_id uuid,
    actor_ip inet,
    actor_user_agent text,
    action character varying(100) NOT NULL,
    resource_type character varying(100) NOT NULL,
    resource_id uuid,
    before_state jsonb,
    after_state jsonb,
    correlation_id uuid,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL
)
PARTITION BY RANGE (occurred_at);


--
-- Name: audit_log_default; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_log_default (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid,
    actor_type public.actor_type NOT NULL,
    actor_id uuid,
    actor_ip inet,
    actor_user_agent text,
    action character varying(100) NOT NULL,
    resource_type character varying(100) NOT NULL,
    resource_id uuid,
    before_state jsonb,
    after_state jsonb,
    correlation_id uuid,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: brand_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.brand_settings (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    brand_name character varying(255) NOT NULL,
    tagline character varying(500),
    voice_config jsonb DEFAULT '{}'::jsonb NOT NULL,
    palette jsonb DEFAULT '{}'::jsonb NOT NULL,
    logo_url text,
    logo_dark_url text,
    typography jsonb DEFAULT '{}'::jsonb NOT NULL,
    forbidden_terms text[] DEFAULT '{}'::text[] NOT NULL,
    required_disclaimers text[] DEFAULT '{}'::text[] NOT NULL,
    competitor_mentions_policy character varying(50) DEFAULT 'forbidden'::character varying NOT NULL,
    primary_language character varying(10) DEFAULT 'en'::character varying NOT NULL,
    supported_languages text[] DEFAULT '{en}'::text[] NOT NULL,
    social_handles jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: campaigns; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.campaigns (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    objective public.campaign_objective NOT NULL,
    channels public.channel_type[] DEFAULT '{}'::public.channel_type[] NOT NULL,
    budget_cents bigint NOT NULL,
    daily_cap_cents bigint NOT NULL,
    spent_cents bigint DEFAULT 0 NOT NULL,
    currency character(3) DEFAULT 'USD'::bpchar NOT NULL,
    starts_at timestamp with time zone,
    ends_at timestamp with time zone,
    status public.campaign_status DEFAULT 'draft'::public.campaign_status NOT NULL,
    auto_pause_rules jsonb DEFAULT '{}'::jsonb NOT NULL,
    owner_approved_at timestamp with time zone,
    owner_approved_by uuid,
    launched_at timestamp with time zone,
    paused_at timestamp with time zone,
    completed_at timestamp with time zone,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: content_assets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_assets (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    template_id uuid,
    campaign_id uuid,
    title character varying(500),
    channel public.channel_type NOT NULL,
    format character varying(50) NOT NULL,
    variants jsonb DEFAULT '[]'::jsonb NOT NULL,
    selected_variant_index integer,
    media_urls jsonb DEFAULT '[]'::jsonb NOT NULL,
    generated_by_model character varying(100),
    generation_prompt_id character varying(100),
    generation_cost_cents integer,
    status public.content_status DEFAULT 'draft'::public.content_status NOT NULL,
    moderation_status character varying(50),
    moderation_details jsonb,
    owner_approved_at timestamp with time zone,
    owner_approved_by uuid,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: content_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_templates (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    channel public.channel_type NOT NULL,
    format character varying(50) NOT NULL,
    body_template text NOT NULL,
    variables jsonb DEFAULT '[]'::jsonb NOT NULL,
    brand_voice_ref uuid,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: conversations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.conversations (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    customer_id uuid,
    channel public.channel_type NOT NULL,
    external_thread_id character varying(255),
    status public.conversation_status DEFAULT 'open'::public.conversation_status NOT NULL,
    assignee_id uuid,
    topic character varying(255),
    sentiment character varying(50),
    priority integer DEFAULT 0 NOT NULL,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    first_response_at timestamp with time zone,
    last_customer_message_at timestamp with time zone,
    last_agent_message_at timestamp with time zone,
    resolved_at timestamp with time zone,
    csat_score integer,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: customers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.customers (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    email public.citext,
    phone character varying(50),
    first_name character varying(100),
    last_name character varying(100),
    country_code character(2),
    city character varying(255),
    default_address jsonb,
    accepts_marketing boolean DEFAULT false NOT NULL,
    consent jsonb DEFAULT '{}'::jsonb NOT NULL,
    lifetime_value_cents bigint DEFAULT 0 NOT NULL,
    order_count integer DEFAULT 0 NOT NULL,
    first_order_at timestamp with time zone,
    last_order_at timestamp with time zone,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    external_ids jsonb DEFAULT '{}'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT customer_contact_required CHECK (((email IS NOT NULL) OR (phone IS NOT NULL)))
);


--
-- Name: email_verification_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.email_verification_tokens (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    token_hash character varying(255) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: faqs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.faqs (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    question text NOT NULL,
    answer text NOT NULL,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    channels public.channel_type[] DEFAULT '{}'::public.channel_type[] NOT NULL,
    language character varying(10) DEFAULT 'en'::character varying NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    priority integer DEFAULT 0 NOT NULL,
    times_used integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: generation_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.generation_jobs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    kind text NOT NULL,
    status text NOT NULL,
    request jsonb NOT NULL,
    effective jsonb DEFAULT '{}'::jsonb NOT NULL,
    provider text,
    model text,
    provider_ref text,
    attempts jsonb DEFAULT '[]'::jsonb NOT NULL,
    result_media_id uuid,
    parent_job_id uuid,
    approved_at timestamp with time zone,
    approved_by uuid,
    cost_cents integer DEFAULT 0 NOT NULL,
    error text,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone,
    CONSTRAINT generation_jobs_kind_check CHECK ((kind = ANY (ARRAY['image'::text, 'video'::text]))),
    CONSTRAINT generation_jobs_status_check CHECK ((status = ANY (ARRAY['queued'::text, 'running'::text, 'succeeded'::text, 'failed'::text, 'cancelled'::text])))
);


--
-- Name: integrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.integrations (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    provider public.integration_provider NOT NULL,
    account_name character varying(255),
    account_external_id character varying(255),
    credentials_ref character varying(255) NOT NULL,
    scopes text[] DEFAULT '{}'::text[] NOT NULL,
    status public.integration_status DEFAULT 'connected'::public.integration_status NOT NULL,
    connected_by uuid,
    connected_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone,
    last_sync_at timestamp with time zone,
    last_error text,
    settings jsonb DEFAULT '{}'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: inventory; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.inventory (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    variant_id uuid NOT NULL,
    location_id uuid NOT NULL,
    on_hand integer DEFAULT 0 NOT NULL,
    committed integer DEFAULT 0 NOT NULL,
    available integer GENERATED ALWAYS AS ((on_hand - committed)) STORED,
    reorder_point integer DEFAULT 10 NOT NULL,
    reorder_qty integer DEFAULT 50 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: inventory_locations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.inventory_locations (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    code character varying(50) NOT NULL,
    address jsonb,
    is_default boolean DEFAULT false NOT NULL,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: inventory_movements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.inventory_movements (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    inventory_id uuid NOT NULL,
    movement_type character varying(50) NOT NULL,
    quantity integer NOT NULL,
    reference_type character varying(50),
    reference_id uuid,
    reason text,
    performed_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: kb_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.kb_documents (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    title character varying(500) NOT NULL,
    body text NOT NULL,
    source character varying(100),
    source_url text,
    document_type character varying(50) DEFAULT 'text'::character varying NOT NULL,
    embedding jsonb,
    embedding_model character varying(100),
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    indexed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: knowledge_embeddings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.knowledge_embeddings (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    source_kind text NOT NULL,
    source_id uuid NOT NULL,
    chunk integer DEFAULT 0 NOT NULL,
    content_hash text NOT NULL,
    model text NOT NULL,
    dims integer NOT NULL,
    embedding real[] NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT knowledge_embeddings_source_kind_check CHECK ((source_kind = ANY (ARRAY['faq'::text, 'policy'::text, 'kb_document'::text])))
);


--
-- Name: macros; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.macros (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    body text NOT NULL,
    variables jsonb DEFAULT '[]'::jsonb NOT NULL,
    channels public.channel_type[] DEFAULT '{}'::public.channel_type[] NOT NULL,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: media_assets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.media_assets (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    kind text NOT NULL,
    mime text NOT NULL,
    bytes bigint NOT NULL,
    width integer,
    height integer,
    duration_ms integer,
    sha256 text NOT NULL,
    storage_key text NOT NULL,
    source text NOT NULL,
    parent_id uuid,
    generation_job_id uuid,
    name text,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT media_assets_kind_check CHECK ((kind = ANY (ARRAY['image'::text, 'video'::text, 'audio'::text]))),
    CONSTRAINT media_assets_source_check CHECK ((source = ANY (ARRAY['upload'::text, 'ai_image'::text, 'ai_video'::text, 'catalog'::text, 'derived'::text])))
);


--
-- Name: messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.messages (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    direction public.message_direction NOT NULL,
    sender_type public.sender_type NOT NULL,
    sender_id uuid,
    body text NOT NULL,
    attachments jsonb DEFAULT '[]'::jsonb NOT NULL,
    external_message_id character varying(255),
    ai_draft_of_id uuid,
    ai_confidence numeric(5,4),
    ai_model character varying(100),
    approved_by uuid,
    approved_at timestamp with time zone,
    sent_at timestamp with time zone,
    delivered_at timestamp with time zone,
    read_at timestamp with time zone,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: notifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notifications (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,
    type character varying(50) NOT NULL,
    title character varying(255) NOT NULL,
    body text,
    link_url text,
    severity character varying(20) DEFAULT 'info'::character varying NOT NULL,
    read_at timestamp with time zone,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: orchestrator_chats; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.orchestrator_chats (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    user_id uuid,
    project_id uuid,
    title text DEFAULT 'New chat'::text NOT NULL,
    title_source text DEFAULT 'auto'::text NOT NULL,
    pinned boolean DEFAULT false NOT NULL,
    archived_at timestamp with time zone,
    deleted_at timestamp with time zone,
    last_message_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: orchestrator_files; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.orchestrator_files (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    user_id uuid,
    message_id uuid,
    name text NOT NULL,
    kind text NOT NULL,
    mime text NOT NULL,
    bytes bigint NOT NULL,
    sha256 text NOT NULL,
    storage_key text NOT NULL,
    status text DEFAULT 'extracted'::text NOT NULL,
    extracted jsonb,
    error text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    project_id uuid
);


--
-- Name: orchestrator_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.orchestrator_messages (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    user_id uuid,
    session_id uuid,
    role character varying(20) NOT NULL,
    content text NOT NULL,
    parsed_intent jsonb,
    llm_model character varying(100),
    tokens_input integer,
    tokens_output integer,
    cost_cents numeric(10,4),
    correlation_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: orchestrator_plans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.orchestrator_plans (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    triggering_message_id uuid,
    correlation_id uuid NOT NULL,
    title character varying(500) NOT NULL,
    description text,
    actions jsonb DEFAULT '[]'::jsonb NOT NULL,
    status public.plan_status DEFAULT 'proposed'::public.plan_status NOT NULL,
    estimated_cost_cents bigint,
    approved_by uuid,
    approved_at timestamp with time zone,
    rejected_by uuid,
    rejected_at timestamp with time zone,
    rejection_reason text,
    executed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    mode text,
    start_at timestamp with time zone,
    concurrency integer,
    submitted_at timestamp with time zone,
    paused_at timestamp with time zone,
    progress_at timestamp with time zone,
    items jsonb,
    template jsonb
);


--
-- Name: orchestrator_projects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.orchestrator_projects (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    created_by uuid,
    name text NOT NULL,
    description text,
    instructions text,
    emoji text,
    archived_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: order_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.order_items (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    order_id uuid NOT NULL,
    variant_id uuid,
    product_snapshot jsonb NOT NULL,
    quantity integer NOT NULL,
    unit_price_cents bigint NOT NULL,
    discount_cents bigint DEFAULT 0 NOT NULL,
    line_total_cents bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT order_items_quantity_check CHECK ((quantity > 0))
);


--
-- Name: orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.orders (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    customer_id uuid,
    order_number character varying(50) NOT NULL,
    channel public.channel_type NOT NULL,
    status public.order_status DEFAULT 'pending'::public.order_status NOT NULL,
    subtotal_cents bigint DEFAULT 0 NOT NULL,
    discount_cents bigint DEFAULT 0 NOT NULL,
    shipping_cents bigint DEFAULT 0 NOT NULL,
    tax_cents bigint DEFAULT 0 NOT NULL,
    total_cents bigint DEFAULT 0 NOT NULL,
    currency character(3) DEFAULT 'USD'::bpchar NOT NULL,
    shipping_address jsonb NOT NULL,
    billing_address jsonb,
    payment_method character varying(50),
    payment_status character varying(50),
    shipping_policy_id uuid,
    tracking_number character varying(255),
    tracking_url text,
    notes text,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    external_id character varying(255),
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    placed_at timestamp with time zone DEFAULT now() NOT NULL,
    fulfilled_at timestamp with time zone,
    delivered_at timestamp with time zone,
    cancelled_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: organic_contents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organic_contents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    title text,
    mode text NOT NULL,
    prompt text,
    caption text DEFAULT ''::text NOT NULL,
    hashtags text[] DEFAULT '{}'::text[] NOT NULL,
    cta text,
    link_url text,
    media_ids uuid[] DEFAULT '{}'::uuid[] NOT NULL,
    product_ids uuid[] DEFAULT '{}'::uuid[] NOT NULL,
    status text DEFAULT 'draft'::text NOT NULL,
    approved_by uuid,
    approved_at timestamp with time zone,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT organic_contents_mode_check CHECK ((mode = ANY (ARRAY['manual'::text, 'ai'::text]))),
    CONSTRAINT organic_contents_status_check CHECK ((status = ANY (ARRAY['draft'::text, 'needs_approval'::text, 'approved'::text, 'archived'::text])))
);


--
-- Name: password_reset_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.password_reset_tokens (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    token_hash character varying(255) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: permissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.permissions (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    code character varying(150) NOT NULL,
    resource character varying(100) NOT NULL,
    action character varying(50) NOT NULL,
    description text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: platform_admins; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_admins (
    user_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: platform_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_settings (
    key text NOT NULL,
    value jsonb DEFAULT '{}'::jsonb NOT NULL,
    updated_by uuid,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: policies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.policies (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    policy_type character varying(50) NOT NULL,
    title character varying(255) NOT NULL,
    body text NOT NULL,
    structured_rules jsonb DEFAULT '{}'::jsonb NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    effective_from timestamp with time zone,
    effective_until timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: pricing_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pricing_rules (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    scope public.pricing_scope NOT NULL,
    scope_ids uuid[] DEFAULT '{}'::uuid[] NOT NULL,
    rule_type public.pricing_rule_type NOT NULL,
    value numeric(12,2) NOT NULL,
    min_quantity integer,
    conditions jsonb DEFAULT '{}'::jsonb NOT NULL,
    starts_at timestamp with time zone,
    ends_at timestamp with time zone,
    priority integer DEFAULT 0 NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: product_categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.product_categories (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    parent_id uuid,
    name character varying(255) NOT NULL,
    slug character varying(255) NOT NULL,
    description text,
    display_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: product_variants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.product_variants (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    product_id uuid NOT NULL,
    sku character varying(100) NOT NULL,
    barcode character varying(100),
    attributes jsonb DEFAULT '{}'::jsonb NOT NULL,
    price_cents bigint NOT NULL,
    compare_at_price_cents bigint,
    cost_cents bigint,
    weight_grams integer,
    images jsonb DEFAULT '[]'::jsonb NOT NULL,
    is_default boolean DEFAULT false NOT NULL,
    display_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: products; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.products (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    sku character varying(100) NOT NULL,
    title character varying(500) NOT NULL,
    slug character varying(500) NOT NULL,
    description text,
    short_description character varying(500),
    category_id uuid,
    brand character varying(255),
    status public.product_status DEFAULT 'draft'::public.product_status NOT NULL,
    default_price_cents bigint NOT NULL,
    compare_at_price_cents bigint,
    cost_cents bigint,
    currency character(3) DEFAULT 'USD'::bpchar NOT NULL,
    weight_grams integer,
    dimensions jsonb,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    images jsonb DEFAULT '[]'::jsonb NOT NULL,
    seo_title character varying(255),
    seo_description character varying(500),
    channels public.channel_type[] DEFAULT '{}'::public.channel_type[] NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    external_ids jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by uuid,
    updated_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone
);


--
-- Name: rate_limit_buckets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rate_limit_buckets (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    provider public.integration_provider NOT NULL,
    bucket_key character varying(255) NOT NULL,
    tokens_available numeric(12,4) NOT NULL,
    max_tokens numeric(12,4) NOT NULL,
    refill_rate numeric(12,4) NOT NULL,
    last_refill_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: refresh_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.refresh_tokens (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    token_hash character varying(255) NOT NULL,
    device_info jsonb DEFAULT '{}'::jsonb NOT NULL,
    ip_address inet,
    user_agent text,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    replaced_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: role_permissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.role_permissions (
    role_id uuid NOT NULL,
    permission_id uuid NOT NULL,
    attributes jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.roles (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid,
    name character varying(100) NOT NULL,
    type public.role_type NOT NULL,
    description text,
    is_system boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: scheduled_posts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scheduled_posts (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    content_asset_id uuid NOT NULL,
    channel public.channel_type NOT NULL,
    scheduled_at timestamp with time zone NOT NULL,
    status public.post_status DEFAULT 'pending'::public.post_status NOT NULL,
    external_post_id character varying(255),
    external_url text,
    published_at timestamp with time zone,
    error_message text,
    retry_count integer DEFAULT 0 NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: shipping_policies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.shipping_policies (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    zone_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    carrier character varying(100) NOT NULL,
    rate_cents bigint NOT NULL,
    free_over_cents bigint,
    cutoff_time time without time zone,
    sla_days_min integer,
    sla_days_max integer,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    source character varying(20) DEFAULT 'local'::character varying NOT NULL,
    external_id character varying(255),
    method_type character varying(30) DEFAULT 'flat_rate'::character varying NOT NULL,
    conditions jsonb DEFAULT '{}'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: shipping_zones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.shipping_zones (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    country_codes character(2)[] DEFAULT '{}'::bpchar[] NOT NULL,
    regions jsonb DEFAULT '[]'::jsonb NOT NULL,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    source character varying(20) DEFAULT 'local'::character varying NOT NULL,
    external_id character varying(255),
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: system_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.system_logs (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid,
    level character varying(20) NOT NULL,
    service character varying(100) NOT NULL,
    message text NOT NULL,
    context jsonb DEFAULT '{}'::jsonb NOT NULL,
    error_stack text,
    correlation_id uuid,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL
)
PARTITION BY RANGE (occurred_at);


--
-- Name: system_logs_default; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.system_logs_default (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid,
    level character varying(20) NOT NULL,
    service character varying(100) NOT NULL,
    message text NOT NULL,
    context jsonb DEFAULT '{}'::jsonb NOT NULL,
    error_stack text,
    correlation_id uuid,
    occurred_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: tenants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tenants (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    name character varying(255) NOT NULL,
    slug character varying(100) NOT NULL,
    subdomain character varying(100) NOT NULL,
    status public.tenant_status DEFAULT 'trial'::public.tenant_status NOT NULL,
    subscription_tier public.subscription_tier DEFAULT 'free'::public.subscription_tier NOT NULL,
    subscription_expires_at timestamp with time zone,
    country_code character(2),
    currency character(3) DEFAULT 'USD'::bpchar NOT NULL,
    timezone character varying(50) DEFAULT 'UTC'::character varying NOT NULL,
    default_language character varying(10) DEFAULT 'en'::character varying NOT NULL,
    max_users integer DEFAULT 5 NOT NULL,
    max_products integer DEFAULT 100 NOT NULL,
    llm_daily_cap_cents integer DEFAULT 500 NOT NULL,
    ad_daily_cap_cents integer DEFAULT 5000 NOT NULL,
    settings jsonb DEFAULT '{}'::jsonb NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT slug_format CHECK (((slug)::text ~ '^[a-z0-9-]+$'::text)),
    CONSTRAINT subdomain_format CHECK (((subdomain)::text ~ '^[a-z0-9-]+$'::text))
);


--
-- Name: usage_metrics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.usage_metrics (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    day date NOT NULL,
    metric_type character varying(50) NOT NULL,
    value numeric(20,4) DEFAULT 0 NOT NULL,
    cost_cents numeric(12,4) DEFAULT 0 NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: user_roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_roles (
    user_id uuid NOT NULL,
    role_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    assigned_by uuid,
    assigned_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    email public.citext NOT NULL,
    password_hash character varying(255) NOT NULL,
    first_name character varying(100),
    last_name character varying(100),
    phone character varying(50),
    avatar_url text,
    status public.user_status DEFAULT 'invited'::public.user_status NOT NULL,
    email_verified boolean DEFAULT false NOT NULL,
    email_verified_at timestamp with time zone,
    two_factor_enabled boolean DEFAULT false NOT NULL,
    two_factor_secret character varying(255),
    last_login_at timestamp with time zone,
    last_login_ip inet,
    failed_login_attempts integer DEFAULT 0 NOT NULL,
    locked_until timestamp with time zone,
    password_changed_at timestamp with time zone DEFAULT now() NOT NULL,
    must_change_password boolean DEFAULT false NOT NULL,
    preferences jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone
);


--
-- Name: webhook_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.webhook_events (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid,
    integration_id uuid,
    provider public.integration_provider NOT NULL,
    event_type character varying(100) NOT NULL,
    external_event_id character varying(255),
    payload jsonb NOT NULL,
    signature character varying(500),
    signature_valid boolean,
    processed_at timestamp with time zone,
    processing_error text,
    received_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: workflow_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflow_runs (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    workflow_id uuid NOT NULL,
    workflow_version integer NOT NULL,
    triggered_by public.actor_type NOT NULL,
    triggered_by_id uuid,
    input jsonb DEFAULT '{}'::jsonb NOT NULL,
    output jsonb,
    status public.run_status DEFAULT 'pending'::public.run_status NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    error_message text,
    correlation_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: workflows; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.workflows (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    tenant_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    trigger_type public.workflow_trigger_type NOT NULL,
    trigger_config jsonb DEFAULT '{}'::jsonb NOT NULL,
    condition_dsl text,
    actions jsonb DEFAULT '[]'::jsonb NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    previous_version_id uuid,
    run_count integer DEFAULT 0 NOT NULL,
    last_run_at timestamp with time zone,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: analytics_events_default; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_events ATTACH PARTITION public.analytics_events_default DEFAULT;


--
-- Name: audit_log_default; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log ATTACH PARTITION public.audit_log_default DEFAULT;


--
-- Name: system_logs_default; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_logs ATTACH PARTITION public.system_logs_default DEFAULT;


--
-- Name: abandoned_carts abandoned_carts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.abandoned_carts
    ADD CONSTRAINT abandoned_carts_pkey PRIMARY KEY (id);


--
-- Name: action_executions action_executions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_executions
    ADD CONSTRAINT action_executions_pkey PRIMARY KEY (id);


--
-- Name: ad_groups ad_groups_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ad_groups
    ADD CONSTRAINT ad_groups_pkey PRIMARY KEY (id);


--
-- Name: ads ads_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ads
    ADD CONSTRAINT ads_pkey PRIMARY KEY (id);


--
-- Name: ai_campaign_runs ai_campaign_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_campaign_runs
    ADD CONSTRAINT ai_campaign_runs_pkey PRIMARY KEY (id);


--
-- Name: analytics_daily_rollups analytics_daily_rollups_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_daily_rollups
    ADD CONSTRAINT analytics_daily_rollups_pkey PRIMARY KEY (id);


--
-- Name: analytics_events analytics_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_events
    ADD CONSTRAINT analytics_events_pkey PRIMARY KEY (id, event_time);


--
-- Name: analytics_events_default analytics_events_default_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_events_default
    ADD CONSTRAINT analytics_events_default_pkey PRIMARY KEY (id, event_time);


--
-- Name: api_keys api_keys_key_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_key_hash_key UNIQUE (key_hash);


--
-- Name: api_keys api_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_pkey PRIMARY KEY (id);


--
-- Name: approval_queue approval_queue_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_queue
    ADD CONSTRAINT approval_queue_pkey PRIMARY KEY (id);


--
-- Name: audiences audiences_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audiences
    ADD CONSTRAINT audiences_pkey PRIMARY KEY (id);


--
-- Name: audit_log audit_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT audit_log_pkey PRIMARY KEY (id, occurred_at);


--
-- Name: audit_log_default audit_log_default_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log_default
    ADD CONSTRAINT audit_log_default_pkey PRIMARY KEY (id, occurred_at);


--
-- Name: brand_settings brand_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.brand_settings
    ADD CONSTRAINT brand_settings_pkey PRIMARY KEY (id);


--
-- Name: brand_settings brand_settings_tenant_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.brand_settings
    ADD CONSTRAINT brand_settings_tenant_unique UNIQUE (tenant_id);


--
-- Name: campaigns campaigns_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaigns
    ADD CONSTRAINT campaigns_pkey PRIMARY KEY (id);


--
-- Name: product_categories categories_tenant_slug_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_categories
    ADD CONSTRAINT categories_tenant_slug_unique UNIQUE (tenant_id, slug);


--
-- Name: content_assets content_assets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_assets
    ADD CONSTRAINT content_assets_pkey PRIMARY KEY (id);


--
-- Name: content_templates content_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_templates
    ADD CONSTRAINT content_templates_pkey PRIMARY KEY (id);


--
-- Name: conversations conversations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_pkey PRIMARY KEY (id);


--
-- Name: customers customers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_pkey PRIMARY KEY (id);


--
-- Name: customers customers_tenant_email_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_tenant_email_unique UNIQUE (tenant_id, email);


--
-- Name: email_verification_tokens email_verification_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_verification_tokens
    ADD CONSTRAINT email_verification_tokens_pkey PRIMARY KEY (id);


--
-- Name: email_verification_tokens email_verification_tokens_token_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_verification_tokens
    ADD CONSTRAINT email_verification_tokens_token_hash_key UNIQUE (token_hash);


--
-- Name: faqs faqs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.faqs
    ADD CONSTRAINT faqs_pkey PRIMARY KEY (id);


--
-- Name: generation_jobs generation_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.generation_jobs
    ADD CONSTRAINT generation_jobs_pkey PRIMARY KEY (id);


--
-- Name: integrations integrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.integrations
    ADD CONSTRAINT integrations_pkey PRIMARY KEY (id);


--
-- Name: integrations integrations_tenant_provider_account; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.integrations
    ADD CONSTRAINT integrations_tenant_provider_account UNIQUE (tenant_id, provider, account_external_id);


--
-- Name: inventory_locations inventory_locations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory_locations
    ADD CONSTRAINT inventory_locations_pkey PRIMARY KEY (id);


--
-- Name: inventory_movements inventory_movements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory_movements
    ADD CONSTRAINT inventory_movements_pkey PRIMARY KEY (id);


--
-- Name: inventory inventory_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory
    ADD CONSTRAINT inventory_pkey PRIMARY KEY (id);


--
-- Name: inventory inventory_variant_location_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory
    ADD CONSTRAINT inventory_variant_location_unique UNIQUE (variant_id, location_id);


--
-- Name: kb_documents kb_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kb_documents
    ADD CONSTRAINT kb_documents_pkey PRIMARY KEY (id);


--
-- Name: knowledge_embeddings knowledge_embeddings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_embeddings
    ADD CONSTRAINT knowledge_embeddings_pkey PRIMARY KEY (id);


--
-- Name: knowledge_embeddings knowledge_embeddings_tenant_id_source_kind_source_id_chunk__key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_embeddings
    ADD CONSTRAINT knowledge_embeddings_tenant_id_source_kind_source_id_chunk__key UNIQUE (tenant_id, source_kind, source_id, chunk, model);


--
-- Name: inventory_locations locations_tenant_code_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory_locations
    ADD CONSTRAINT locations_tenant_code_unique UNIQUE (tenant_id, code);


--
-- Name: macros macros_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.macros
    ADD CONSTRAINT macros_pkey PRIMARY KEY (id);


--
-- Name: media_assets media_assets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.media_assets
    ADD CONSTRAINT media_assets_pkey PRIMARY KEY (id);


--
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id);


--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


--
-- Name: orchestrator_chats orchestrator_chats_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestrator_chats
    ADD CONSTRAINT orchestrator_chats_pkey PRIMARY KEY (id);


--
-- Name: orchestrator_files orchestrator_files_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestrator_files
    ADD CONSTRAINT orchestrator_files_pkey PRIMARY KEY (id);


--
-- Name: orchestrator_messages orchestrator_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestrator_messages
    ADD CONSTRAINT orchestrator_messages_pkey PRIMARY KEY (id);


--
-- Name: orchestrator_plans orchestrator_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestrator_plans
    ADD CONSTRAINT orchestrator_plans_pkey PRIMARY KEY (id);


--
-- Name: orchestrator_projects orchestrator_projects_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestrator_projects
    ADD CONSTRAINT orchestrator_projects_pkey PRIMARY KEY (id);


--
-- Name: order_items order_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_pkey PRIMARY KEY (id);


--
-- Name: orders orders_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_pkey PRIMARY KEY (id);


--
-- Name: orders orders_tenant_number_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_tenant_number_unique UNIQUE (tenant_id, order_number);


--
-- Name: organic_contents organic_contents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organic_contents
    ADD CONSTRAINT organic_contents_pkey PRIMARY KEY (id);


--
-- Name: password_reset_tokens password_reset_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_pkey PRIMARY KEY (id);


--
-- Name: password_reset_tokens password_reset_tokens_token_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_token_hash_key UNIQUE (token_hash);


--
-- Name: permissions permissions_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.permissions
    ADD CONSTRAINT permissions_code_key UNIQUE (code);


--
-- Name: permissions permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.permissions
    ADD CONSTRAINT permissions_pkey PRIMARY KEY (id);


--
-- Name: platform_admins platform_admins_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_admins
    ADD CONSTRAINT platform_admins_pkey PRIMARY KEY (user_id);


--
-- Name: platform_settings platform_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_settings
    ADD CONSTRAINT platform_settings_pkey PRIMARY KEY (key);


--
-- Name: policies policies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policies
    ADD CONSTRAINT policies_pkey PRIMARY KEY (id);


--
-- Name: pricing_rules pricing_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pricing_rules
    ADD CONSTRAINT pricing_rules_pkey PRIMARY KEY (id);


--
-- Name: product_categories product_categories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_categories
    ADD CONSTRAINT product_categories_pkey PRIMARY KEY (id);


--
-- Name: product_variants product_variants_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_variants
    ADD CONSTRAINT product_variants_pkey PRIMARY KEY (id);


--
-- Name: products products_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_pkey PRIMARY KEY (id);


--
-- Name: products products_tenant_sku_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_tenant_sku_unique UNIQUE (tenant_id, sku);


--
-- Name: products products_tenant_slug_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_tenant_slug_unique UNIQUE (tenant_id, slug);


--
-- Name: rate_limit_buckets rate_limit_buckets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rate_limit_buckets
    ADD CONSTRAINT rate_limit_buckets_pkey PRIMARY KEY (id);


--
-- Name: rate_limit_buckets rate_limit_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rate_limit_buckets
    ADD CONSTRAINT rate_limit_unique UNIQUE (tenant_id, provider, bucket_key);


--
-- Name: refresh_tokens refresh_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_pkey PRIMARY KEY (id);


--
-- Name: refresh_tokens refresh_tokens_token_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_token_hash_key UNIQUE (token_hash);


--
-- Name: role_permissions role_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_pkey PRIMARY KEY (role_id, permission_id);


--
-- Name: roles roles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (id);


--
-- Name: roles roles_tenant_name_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_tenant_name_unique UNIQUE (tenant_id, name);


--
-- Name: analytics_daily_rollups rollup_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_daily_rollups
    ADD CONSTRAINT rollup_unique UNIQUE (tenant_id, day, entity_type, entity_id, channel, metric, dimensions);


--
-- Name: scheduled_posts scheduled_posts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheduled_posts
    ADD CONSTRAINT scheduled_posts_pkey PRIMARY KEY (id);


--
-- Name: shipping_policies shipping_policies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shipping_policies
    ADD CONSTRAINT shipping_policies_pkey PRIMARY KEY (id);


--
-- Name: shipping_zones shipping_zones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shipping_zones
    ADD CONSTRAINT shipping_zones_pkey PRIMARY KEY (id);


--
-- Name: system_logs system_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_logs
    ADD CONSTRAINT system_logs_pkey PRIMARY KEY (id, occurred_at);


--
-- Name: system_logs_default system_logs_default_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_logs_default
    ADD CONSTRAINT system_logs_default_pkey PRIMARY KEY (id, occurred_at);


--
-- Name: tenants tenants_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT tenants_pkey PRIMARY KEY (id);


--
-- Name: tenants tenants_slug_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT tenants_slug_key UNIQUE (slug);


--
-- Name: tenants tenants_subdomain_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT tenants_subdomain_key UNIQUE (subdomain);


--
-- Name: usage_metrics usage_metrics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usage_metrics
    ADD CONSTRAINT usage_metrics_pkey PRIMARY KEY (id);


--
-- Name: usage_metrics usage_metrics_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usage_metrics
    ADD CONSTRAINT usage_metrics_unique UNIQUE (tenant_id, day, metric_type);


--
-- Name: user_roles user_roles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_pkey PRIMARY KEY (user_id, role_id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_tenant_email_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_tenant_email_unique UNIQUE (tenant_id, email);


--
-- Name: product_variants variants_tenant_sku_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_variants
    ADD CONSTRAINT variants_tenant_sku_unique UNIQUE (tenant_id, sku);


--
-- Name: webhook_events webhook_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.webhook_events
    ADD CONSTRAINT webhook_events_pkey PRIMARY KEY (id);


--
-- Name: workflow_runs workflow_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_runs
    ADD CONSTRAINT workflow_runs_pkey PRIMARY KEY (id);


--
-- Name: workflows workflows_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflows
    ADD CONSTRAINT workflows_pkey PRIMARY KEY (id);


--
-- Name: idx_analytics_events_entity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_analytics_events_entity ON ONLY public.analytics_events USING btree (tenant_id, entity_type, entity_id, event_time DESC);


--
-- Name: analytics_events_default_tenant_id_entity_type_entity_id_ev_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX analytics_events_default_tenant_id_entity_type_entity_id_ev_idx ON public.analytics_events_default USING btree (tenant_id, entity_type, entity_id, event_time DESC);


--
-- Name: idx_analytics_events_tenant_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_analytics_events_tenant_time ON ONLY public.analytics_events USING btree (tenant_id, event_time DESC);


--
-- Name: analytics_events_default_tenant_id_event_time_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX analytics_events_default_tenant_id_event_time_idx ON public.analytics_events_default USING btree (tenant_id, event_time DESC);


--
-- Name: idx_analytics_events_metric; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_analytics_events_metric ON ONLY public.analytics_events USING btree (tenant_id, metric, event_time DESC);


--
-- Name: analytics_events_default_tenant_id_metric_event_time_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX analytics_events_default_tenant_id_metric_event_time_idx ON public.analytics_events_default USING btree (tenant_id, metric, event_time DESC);


--
-- Name: idx_audit_log_actor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_log_actor ON ONLY public.audit_log USING btree (actor_type, actor_id, occurred_at DESC);


--
-- Name: audit_log_default_actor_type_actor_id_occurred_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX audit_log_default_actor_type_actor_id_occurred_at_idx ON public.audit_log_default USING btree (actor_type, actor_id, occurred_at DESC);


--
-- Name: idx_audit_log_correlation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_log_correlation ON ONLY public.audit_log USING btree (correlation_id) WHERE (correlation_id IS NOT NULL);


--
-- Name: audit_log_default_correlation_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX audit_log_default_correlation_id_idx ON public.audit_log_default USING btree (correlation_id) WHERE (correlation_id IS NOT NULL);


--
-- Name: idx_audit_log_resource; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_log_resource ON ONLY public.audit_log USING btree (resource_type, resource_id, occurred_at DESC);


--
-- Name: audit_log_default_resource_type_resource_id_occurred_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX audit_log_default_resource_type_resource_id_occurred_at_idx ON public.audit_log_default USING btree (resource_type, resource_id, occurred_at DESC);


--
-- Name: idx_audit_log_tenant_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_log_tenant_time ON ONLY public.audit_log USING btree (tenant_id, occurred_at DESC);


--
-- Name: audit_log_default_tenant_id_occurred_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX audit_log_default_tenant_id_occurred_at_idx ON public.audit_log_default USING btree (tenant_id, occurred_at DESC);


--
-- Name: generation_jobs_tenant_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX generation_jobs_tenant_idx ON public.generation_jobs USING btree (tenant_id, created_at DESC);


--
-- Name: idx_abandoned_carts_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_abandoned_carts_tenant ON public.abandoned_carts USING btree (tenant_id, abandoned_at DESC) WHERE (recovered_at IS NULL);


--
-- Name: idx_action_exec_idempotency; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_action_exec_idempotency ON public.action_executions USING btree (idempotency_key) WHERE (idempotency_key IS NOT NULL);


--
-- Name: idx_action_exec_retry; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_action_exec_retry ON public.action_executions USING btree (next_retry_at) WHERE (status = 'retrying'::public.run_status);


--
-- Name: idx_action_exec_run; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_action_exec_run ON public.action_executions USING btree (workflow_run_id, action_index);


--
-- Name: idx_action_executions_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_action_executions_tenant ON public.action_executions USING btree (tenant_id);


--
-- Name: idx_ad_groups_audience; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ad_groups_audience ON public.ad_groups USING btree (audience_id);


--
-- Name: idx_ad_groups_campaign; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ad_groups_campaign ON public.ad_groups USING btree (campaign_id);


--
-- Name: idx_ad_groups_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ad_groups_tenant ON public.ad_groups USING btree (tenant_id);


--
-- Name: idx_ads_content_asset; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ads_content_asset ON public.ads USING btree (content_asset_id);


--
-- Name: idx_ads_group; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ads_group ON public.ads USING btree (ad_group_id);


--
-- Name: idx_ads_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ads_tenant ON public.ads USING btree (tenant_id);


--
-- Name: idx_ai_campaign_runs_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ai_campaign_runs_tenant ON public.ai_campaign_runs USING btree (tenant_id, created_at DESC);


--
-- Name: idx_ai_campaign_runs_tenant_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ai_campaign_runs_tenant_status ON public.ai_campaign_runs USING btree (tenant_id, status);


--
-- Name: idx_api_keys_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_api_keys_tenant ON public.api_keys USING btree (tenant_id) WHERE (revoked_at IS NULL);


--
-- Name: idx_approvals_subject; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_approvals_subject ON public.approval_queue USING btree (subject_type, subject_id);


--
-- Name: idx_approvals_tenant_pending; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_approvals_tenant_pending ON public.approval_queue USING btree (tenant_id, requested_at DESC) WHERE (decision = 'pending'::public.approval_decision);


--
-- Name: idx_audiences_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audiences_tenant ON public.audiences USING btree (tenant_id);


--
-- Name: idx_campaigns_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaigns_active ON public.campaigns USING btree (tenant_id, starts_at, ends_at) WHERE (status = 'running'::public.campaign_status);


--
-- Name: idx_campaigns_tenant_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_campaigns_tenant_status ON public.campaigns USING btree (tenant_id, status);


--
-- Name: idx_categories_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_categories_tenant ON public.product_categories USING btree (tenant_id);


--
-- Name: idx_content_assets_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_assets_status ON public.content_assets USING btree (tenant_id, status);


--
-- Name: idx_content_assets_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_assets_tenant ON public.content_assets USING btree (tenant_id, created_at DESC);


--
-- Name: idx_content_templates_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_content_templates_tenant ON public.content_templates USING btree (tenant_id, channel) WHERE (enabled = true);


--
-- Name: idx_conversations_assignee; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_assignee ON public.conversations USING btree (assignee_id) WHERE (status = ANY (ARRAY['open'::public.conversation_status, 'pending'::public.conversation_status]));


--
-- Name: idx_conversations_customer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_customer ON public.conversations USING btree (customer_id, created_at DESC);


--
-- Name: idx_conversations_tenant_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conversations_tenant_status ON public.conversations USING btree (tenant_id, status, updated_at DESC) WHERE (status = ANY (ARRAY['open'::public.conversation_status, 'pending'::public.conversation_status]));


--
-- Name: idx_customers_phone; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_customers_phone ON public.customers USING btree (tenant_id, phone) WHERE (phone IS NOT NULL);


--
-- Name: idx_customers_tags; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_customers_tags ON public.customers USING gin (tags);


--
-- Name: idx_customers_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_customers_tenant ON public.customers USING btree (tenant_id) WHERE (deleted_at IS NULL);


--
-- Name: idx_faqs_question_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_faqs_question_trgm ON public.faqs USING gin (question public.gin_trgm_ops);


--
-- Name: idx_faqs_tags; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_faqs_tags ON public.faqs USING gin (tags);


--
-- Name: idx_faqs_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_faqs_tenant ON public.faqs USING btree (tenant_id) WHERE (enabled = true);


--
-- Name: idx_integrations_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_integrations_status ON public.integrations USING btree (tenant_id, status);


--
-- Name: idx_integrations_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_integrations_tenant ON public.integrations USING btree (tenant_id, provider);


--
-- Name: idx_inventory_low_stock; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_inventory_low_stock ON public.inventory USING btree (tenant_id) WHERE (available <= reorder_point);


--
-- Name: idx_inventory_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_inventory_tenant ON public.inventory USING btree (tenant_id);


--
-- Name: idx_kb_documents_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_kb_documents_tenant ON public.kb_documents USING btree (tenant_id);


--
-- Name: idx_macros_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_macros_tenant ON public.macros USING btree (tenant_id) WHERE (enabled = true);


--
-- Name: idx_messages_conversation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_messages_conversation ON public.messages USING btree (conversation_id, created_at DESC);


--
-- Name: idx_messages_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_messages_tenant ON public.messages USING btree (tenant_id, created_at DESC);


--
-- Name: idx_movements_tenant_inv; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_movements_tenant_inv ON public.inventory_movements USING btree (tenant_id, inventory_id, created_at DESC);


--
-- Name: idx_notifications_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_notifications_tenant ON public.notifications USING btree (tenant_id);


--
-- Name: idx_notifications_user_unread; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_notifications_user_unread ON public.notifications USING btree (user_id, created_at DESC) WHERE (read_at IS NULL);


--
-- Name: idx_orchestrator_messages_correlation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_orchestrator_messages_correlation ON public.orchestrator_messages USING btree (correlation_id);


--
-- Name: idx_orchestrator_messages_session; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_orchestrator_messages_session ON public.orchestrator_messages USING btree (session_id, created_at);


--
-- Name: idx_orchestrator_messages_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_orchestrator_messages_tenant ON public.orchestrator_messages USING btree (tenant_id, created_at DESC);


--
-- Name: idx_order_items_order; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_order_items_order ON public.order_items USING btree (order_id);


--
-- Name: idx_order_items_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_order_items_tenant ON public.order_items USING btree (tenant_id);


--
-- Name: idx_order_items_variant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_order_items_variant ON public.order_items USING btree (variant_id);


--
-- Name: idx_orders_channel; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_orders_channel ON public.orders USING btree (tenant_id, channel, status, created_at DESC);


--
-- Name: idx_orders_customer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_orders_customer ON public.orders USING btree (customer_id, created_at DESC);


--
-- Name: idx_orders_tenant_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_orders_tenant_created ON public.orders USING btree (tenant_id, created_at DESC);


--
-- Name: idx_orders_tenant_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_orders_tenant_status ON public.orders USING btree (tenant_id, status, created_at DESC);


--
-- Name: idx_password_reset_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_password_reset_user ON public.password_reset_tokens USING btree (user_id) WHERE (used_at IS NULL);


--
-- Name: idx_permissions_resource; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_permissions_resource ON public.permissions USING btree (resource);


--
-- Name: idx_plans_correlation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_plans_correlation ON public.orchestrator_plans USING btree (correlation_id);


--
-- Name: idx_plans_tenant_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_plans_tenant_status ON public.orchestrator_plans USING btree (tenant_id, status, created_at DESC);


--
-- Name: idx_policies_tenant_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_policies_tenant_type ON public.policies USING btree (tenant_id, policy_type) WHERE (enabled = true);


--
-- Name: idx_pricing_rules_active_window; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pricing_rules_active_window ON public.pricing_rules USING btree (tenant_id, starts_at, ends_at) WHERE (enabled = true);


--
-- Name: idx_pricing_rules_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pricing_rules_tenant ON public.pricing_rules USING btree (tenant_id, priority DESC) WHERE (enabled = true);


--
-- Name: idx_products_tags; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_products_tags ON public.products USING gin (tags);


--
-- Name: idx_products_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_products_tenant ON public.products USING btree (tenant_id) WHERE (deleted_at IS NULL);


--
-- Name: idx_products_tenant_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_products_tenant_status ON public.products USING btree (tenant_id, status) WHERE (deleted_at IS NULL);


--
-- Name: idx_products_title_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_products_title_trgm ON public.products USING gin (title public.gin_trgm_ops);


--
-- Name: idx_refresh_tokens_expires; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_refresh_tokens_expires ON public.refresh_tokens USING btree (expires_at) WHERE (revoked_at IS NULL);


--
-- Name: idx_refresh_tokens_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_refresh_tokens_tenant ON public.refresh_tokens USING btree (tenant_id);


--
-- Name: idx_refresh_tokens_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_refresh_tokens_user ON public.refresh_tokens USING btree (user_id) WHERE (revoked_at IS NULL);


--
-- Name: idx_refresh_tokens_user_all; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_refresh_tokens_user_all ON public.refresh_tokens USING btree (user_id);


--
-- Name: idx_roles_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_roles_tenant ON public.roles USING btree (tenant_id);


--
-- Name: idx_rollups_metric; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rollups_metric ON public.analytics_daily_rollups USING btree (tenant_id, metric, day DESC);


--
-- Name: idx_rollups_tenant_day; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rollups_tenant_day ON public.analytics_daily_rollups USING btree (tenant_id, day DESC);


--
-- Name: idx_scheduled_posts_pending; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_scheduled_posts_pending ON public.scheduled_posts USING btree (scheduled_at) WHERE (status = 'pending'::public.post_status);


--
-- Name: idx_scheduled_posts_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_scheduled_posts_tenant ON public.scheduled_posts USING btree (tenant_id, scheduled_at DESC);


--
-- Name: idx_shipping_policies_zone; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_shipping_policies_zone ON public.shipping_policies USING btree (zone_id) WHERE (active = true);


--
-- Name: idx_shipping_zones_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_shipping_zones_tenant ON public.shipping_zones USING btree (tenant_id) WHERE (active = true);


--
-- Name: idx_system_logs_level; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_system_logs_level ON ONLY public.system_logs USING btree (level, occurred_at DESC) WHERE ((level)::text = ANY ((ARRAY['ERROR'::character varying, 'CRITICAL'::character varying])::text[]));


--
-- Name: idx_system_logs_tenant_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_system_logs_tenant_time ON ONLY public.system_logs USING btree (tenant_id, occurred_at DESC);


--
-- Name: idx_tenants_slug; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tenants_slug ON public.tenants USING btree (slug) WHERE (deleted_at IS NULL);


--
-- Name: idx_tenants_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tenants_status ON public.tenants USING btree (status) WHERE (deleted_at IS NULL);


--
-- Name: idx_usage_metrics_tenant_day; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_usage_metrics_tenant_day ON public.usage_metrics USING btree (tenant_id, day DESC);


--
-- Name: idx_user_roles_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_roles_tenant ON public.user_roles USING btree (tenant_id);


--
-- Name: idx_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_email ON public.users USING btree (email) WHERE (deleted_at IS NULL);


--
-- Name: idx_users_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_status ON public.users USING btree (tenant_id, status) WHERE (deleted_at IS NULL);


--
-- Name: idx_users_tenant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_tenant_id ON public.users USING btree (tenant_id) WHERE (deleted_at IS NULL);


--
-- Name: idx_variants_product; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_variants_product ON public.product_variants USING btree (product_id);


--
-- Name: idx_variants_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_variants_tenant ON public.product_variants USING btree (tenant_id);


--
-- Name: idx_webhook_events_provider; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_webhook_events_provider ON public.webhook_events USING btree (provider, event_type, received_at DESC);


--
-- Name: idx_webhook_events_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_webhook_events_tenant ON public.webhook_events USING btree (tenant_id);


--
-- Name: idx_webhook_events_unprocessed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_webhook_events_unprocessed ON public.webhook_events USING btree (received_at) WHERE (processed_at IS NULL);


--
-- Name: idx_workflow_runs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_runs_status ON public.workflow_runs USING btree (tenant_id, status) WHERE (status = ANY (ARRAY['pending'::public.run_status, 'running'::public.run_status, 'retrying'::public.run_status]));


--
-- Name: idx_workflow_runs_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_runs_tenant ON public.workflow_runs USING btree (tenant_id, created_at DESC);


--
-- Name: idx_workflow_runs_workflow; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflow_runs_workflow ON public.workflow_runs USING btree (workflow_id, created_at DESC);


--
-- Name: idx_workflows_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflows_enabled ON public.workflows USING btree (tenant_id, enabled);


--
-- Name: idx_workflows_tenant_trigger; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_workflows_tenant_trigger ON public.workflows USING btree (tenant_id, trigger_type) WHERE (enabled = true);


--
-- Name: ix_knowledge_embeddings_tenant_model; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_knowledge_embeddings_tenant_model ON public.knowledge_embeddings USING btree (tenant_id, model);


--
-- Name: media_assets_dedupe; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX media_assets_dedupe ON public.media_assets USING btree (tenant_id, sha256, source) WHERE (deleted_at IS NULL);


--
-- Name: media_assets_tenant_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX media_assets_tenant_idx ON public.media_assets USING btree (tenant_id, created_at DESC) WHERE (deleted_at IS NULL);


--
-- Name: orchestrator_chats_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX orchestrator_chats_user ON public.orchestrator_chats USING btree (tenant_id, user_id, last_message_at DESC);


--
-- Name: orchestrator_files_tenant; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX orchestrator_files_tenant ON public.orchestrator_files USING btree (tenant_id, created_at DESC);


--
-- Name: orchestrator_projects_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX orchestrator_projects_user ON public.orchestrator_projects USING btree (tenant_id, created_by);


--
-- Name: shipping_policies_source_external; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX shipping_policies_source_external ON public.shipping_policies USING btree (tenant_id, source, external_id) WHERE (external_id IS NOT NULL);


--
-- Name: shipping_zones_source_external; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX shipping_zones_source_external ON public.shipping_zones USING btree (tenant_id, source, external_id) WHERE (external_id IS NOT NULL);


--
-- Name: system_logs_default_level_occurred_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX system_logs_default_level_occurred_at_idx ON public.system_logs_default USING btree (level, occurred_at DESC) WHERE ((level)::text = ANY ((ARRAY['ERROR'::character varying, 'CRITICAL'::character varying])::text[]));


--
-- Name: system_logs_default_tenant_id_occurred_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX system_logs_default_tenant_id_occurred_at_idx ON public.system_logs_default USING btree (tenant_id, occurred_at DESC);


--
-- Name: analytics_events_default_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.analytics_events_pkey ATTACH PARTITION public.analytics_events_default_pkey;


--
-- Name: analytics_events_default_tenant_id_entity_type_entity_id_ev_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_analytics_events_entity ATTACH PARTITION public.analytics_events_default_tenant_id_entity_type_entity_id_ev_idx;


--
-- Name: analytics_events_default_tenant_id_event_time_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_analytics_events_tenant_time ATTACH PARTITION public.analytics_events_default_tenant_id_event_time_idx;


--
-- Name: analytics_events_default_tenant_id_metric_event_time_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_analytics_events_metric ATTACH PARTITION public.analytics_events_default_tenant_id_metric_event_time_idx;


--
-- Name: audit_log_default_actor_type_actor_id_occurred_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_audit_log_actor ATTACH PARTITION public.audit_log_default_actor_type_actor_id_occurred_at_idx;


--
-- Name: audit_log_default_correlation_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_audit_log_correlation ATTACH PARTITION public.audit_log_default_correlation_id_idx;


--
-- Name: audit_log_default_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.audit_log_pkey ATTACH PARTITION public.audit_log_default_pkey;


--
-- Name: audit_log_default_resource_type_resource_id_occurred_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_audit_log_resource ATTACH PARTITION public.audit_log_default_resource_type_resource_id_occurred_at_idx;


--
-- Name: audit_log_default_tenant_id_occurred_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_audit_log_tenant_time ATTACH PARTITION public.audit_log_default_tenant_id_occurred_at_idx;


--
-- Name: system_logs_default_level_occurred_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_system_logs_level ATTACH PARTITION public.system_logs_default_level_occurred_at_idx;


--
-- Name: system_logs_default_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.system_logs_pkey ATTACH PARTITION public.system_logs_default_pkey;


--
-- Name: system_logs_default_tenant_id_occurred_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.idx_system_logs_tenant_time ATTACH PARTITION public.system_logs_default_tenant_id_occurred_at_idx;


--
-- Name: ad_groups trg_ad_groups_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_ad_groups_updated_at BEFORE UPDATE ON public.ad_groups FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: ads trg_ads_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_ads_updated_at BEFORE UPDATE ON public.ads FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: ai_campaign_runs trg_ai_campaign_runs_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_ai_campaign_runs_updated_at BEFORE UPDATE ON public.ai_campaign_runs FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: analytics_daily_rollups trg_analytics_daily_rollups_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_analytics_daily_rollups_updated_at BEFORE UPDATE ON public.analytics_daily_rollups FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: audiences trg_audiences_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_audiences_updated_at BEFORE UPDATE ON public.audiences FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: brand_settings trg_brand_settings_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_brand_settings_updated_at BEFORE UPDATE ON public.brand_settings FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: campaigns trg_campaigns_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_campaigns_updated_at BEFORE UPDATE ON public.campaigns FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: content_assets trg_content_assets_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_content_assets_updated_at BEFORE UPDATE ON public.content_assets FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: content_templates trg_content_templates_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_content_templates_updated_at BEFORE UPDATE ON public.content_templates FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: conversations trg_conversations_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_conversations_updated_at BEFORE UPDATE ON public.conversations FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: customers trg_customers_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_customers_updated_at BEFORE UPDATE ON public.customers FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: faqs trg_faqs_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_faqs_updated_at BEFORE UPDATE ON public.faqs FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: integrations trg_integrations_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_integrations_updated_at BEFORE UPDATE ON public.integrations FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: inventory_locations trg_inventory_locations_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_inventory_locations_updated_at BEFORE UPDATE ON public.inventory_locations FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: inventory trg_inventory_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_inventory_updated_at BEFORE UPDATE ON public.inventory FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: kb_documents trg_kb_documents_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_kb_documents_updated_at BEFORE UPDATE ON public.kb_documents FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: macros trg_macros_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_macros_updated_at BEFORE UPDATE ON public.macros FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: orchestrator_plans trg_orchestrator_plans_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_orchestrator_plans_updated_at BEFORE UPDATE ON public.orchestrator_plans FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: orders trg_orders_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_orders_updated_at BEFORE UPDATE ON public.orders FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: organic_contents trg_organic_contents_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_organic_contents_updated_at BEFORE UPDATE ON public.organic_contents FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: policies trg_policies_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_policies_updated_at BEFORE UPDATE ON public.policies FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: pricing_rules trg_pricing_rules_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_pricing_rules_updated_at BEFORE UPDATE ON public.pricing_rules FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: product_categories trg_product_categories_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_product_categories_updated_at BEFORE UPDATE ON public.product_categories FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: product_variants trg_product_variants_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_product_variants_updated_at BEFORE UPDATE ON public.product_variants FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: products trg_products_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_products_updated_at BEFORE UPDATE ON public.products FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: rate_limit_buckets trg_rate_limit_buckets_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_rate_limit_buckets_updated_at BEFORE UPDATE ON public.rate_limit_buckets FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: roles trg_roles_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_roles_updated_at BEFORE UPDATE ON public.roles FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: scheduled_posts trg_scheduled_posts_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_scheduled_posts_updated_at BEFORE UPDATE ON public.scheduled_posts FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: shipping_policies trg_shipping_policies_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_shipping_policies_updated_at BEFORE UPDATE ON public.shipping_policies FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: shipping_zones trg_shipping_zones_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_shipping_zones_updated_at BEFORE UPDATE ON public.shipping_zones FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: tenants trg_tenants_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_tenants_updated_at BEFORE UPDATE ON public.tenants FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: usage_metrics trg_usage_metrics_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_usage_metrics_updated_at BEFORE UPDATE ON public.usage_metrics FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: users trg_users_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON public.users FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: workflows trg_workflows_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_workflows_updated_at BEFORE UPDATE ON public.workflows FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: abandoned_carts abandoned_carts_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.abandoned_carts
    ADD CONSTRAINT abandoned_carts_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE SET NULL;


--
-- Name: abandoned_carts abandoned_carts_recovered_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.abandoned_carts
    ADD CONSTRAINT abandoned_carts_recovered_order_id_fkey FOREIGN KEY (recovered_order_id) REFERENCES public.orders(id);


--
-- Name: abandoned_carts abandoned_carts_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.abandoned_carts
    ADD CONSTRAINT abandoned_carts_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: action_executions action_executions_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_executions
    ADD CONSTRAINT action_executions_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: action_executions action_executions_workflow_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_executions
    ADD CONSTRAINT action_executions_workflow_run_id_fkey FOREIGN KEY (workflow_run_id) REFERENCES public.workflow_runs(id) ON DELETE CASCADE;


--
-- Name: ad_groups ad_groups_audience_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ad_groups
    ADD CONSTRAINT ad_groups_audience_id_fkey FOREIGN KEY (audience_id) REFERENCES public.audiences(id) ON DELETE SET NULL;


--
-- Name: ad_groups ad_groups_campaign_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ad_groups
    ADD CONSTRAINT ad_groups_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.campaigns(id) ON DELETE CASCADE;


--
-- Name: ad_groups ad_groups_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ad_groups
    ADD CONSTRAINT ad_groups_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: ads ads_ad_group_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ads
    ADD CONSTRAINT ads_ad_group_id_fkey FOREIGN KEY (ad_group_id) REFERENCES public.ad_groups(id) ON DELETE CASCADE;


--
-- Name: ads ads_content_asset_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ads
    ADD CONSTRAINT ads_content_asset_id_fkey FOREIGN KEY (content_asset_id) REFERENCES public.content_assets(id) ON DELETE SET NULL;


--
-- Name: ads ads_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ads
    ADD CONSTRAINT ads_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: ai_campaign_runs ai_campaign_runs_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_campaign_runs
    ADD CONSTRAINT ai_campaign_runs_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: ai_campaign_runs ai_campaign_runs_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_campaign_runs
    ADD CONSTRAINT ai_campaign_runs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id);


--
-- Name: analytics_daily_rollups analytics_daily_rollups_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics_daily_rollups
    ADD CONSTRAINT analytics_daily_rollups_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: api_keys api_keys_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: api_keys api_keys_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: approval_queue approval_queue_decided_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_queue
    ADD CONSTRAINT approval_queue_decided_by_fkey FOREIGN KEY (decided_by) REFERENCES public.users(id);


--
-- Name: approval_queue approval_queue_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_queue
    ADD CONSTRAINT approval_queue_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: audiences audiences_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audiences
    ADD CONSTRAINT audiences_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: audiences audiences_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audiences
    ADD CONSTRAINT audiences_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: brand_settings brand_settings_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.brand_settings
    ADD CONSTRAINT brand_settings_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: campaigns campaigns_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaigns
    ADD CONSTRAINT campaigns_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: campaigns campaigns_owner_approved_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaigns
    ADD CONSTRAINT campaigns_owner_approved_by_fkey FOREIGN KEY (owner_approved_by) REFERENCES public.users(id);


--
-- Name: campaigns campaigns_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.campaigns
    ADD CONSTRAINT campaigns_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: content_assets content_assets_owner_approved_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_assets
    ADD CONSTRAINT content_assets_owner_approved_by_fkey FOREIGN KEY (owner_approved_by) REFERENCES public.users(id);


--
-- Name: content_assets content_assets_template_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_assets
    ADD CONSTRAINT content_assets_template_id_fkey FOREIGN KEY (template_id) REFERENCES public.content_templates(id) ON DELETE SET NULL;


--
-- Name: content_assets content_assets_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_assets
    ADD CONSTRAINT content_assets_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: content_templates content_templates_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_templates
    ADD CONSTRAINT content_templates_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: content_templates content_templates_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_templates
    ADD CONSTRAINT content_templates_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: conversations conversations_assignee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_assignee_id_fkey FOREIGN KEY (assignee_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: conversations conversations_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE SET NULL;


--
-- Name: conversations conversations_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: customers customers_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: email_verification_tokens email_verification_tokens_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_verification_tokens
    ADD CONSTRAINT email_verification_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: faqs faqs_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.faqs
    ADD CONSTRAINT faqs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: generation_jobs generation_jobs_approved_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.generation_jobs
    ADD CONSTRAINT generation_jobs_approved_by_fkey FOREIGN KEY (approved_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: generation_jobs generation_jobs_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.generation_jobs
    ADD CONSTRAINT generation_jobs_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: generation_jobs generation_jobs_parent_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.generation_jobs
    ADD CONSTRAINT generation_jobs_parent_job_id_fkey FOREIGN KEY (parent_job_id) REFERENCES public.generation_jobs(id) ON DELETE SET NULL;


--
-- Name: generation_jobs generation_jobs_result_media_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.generation_jobs
    ADD CONSTRAINT generation_jobs_result_media_id_fkey FOREIGN KEY (result_media_id) REFERENCES public.media_assets(id) ON DELETE SET NULL;


--
-- Name: generation_jobs generation_jobs_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.generation_jobs
    ADD CONSTRAINT generation_jobs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: integrations integrations_connected_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.integrations
    ADD CONSTRAINT integrations_connected_by_fkey FOREIGN KEY (connected_by) REFERENCES public.users(id);


--
-- Name: integrations integrations_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.integrations
    ADD CONSTRAINT integrations_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: inventory inventory_location_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory
    ADD CONSTRAINT inventory_location_id_fkey FOREIGN KEY (location_id) REFERENCES public.inventory_locations(id) ON DELETE CASCADE;


--
-- Name: inventory_locations inventory_locations_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory_locations
    ADD CONSTRAINT inventory_locations_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: inventory_movements inventory_movements_inventory_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory_movements
    ADD CONSTRAINT inventory_movements_inventory_id_fkey FOREIGN KEY (inventory_id) REFERENCES public.inventory(id) ON DELETE CASCADE;


--
-- Name: inventory_movements inventory_movements_performed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory_movements
    ADD CONSTRAINT inventory_movements_performed_by_fkey FOREIGN KEY (performed_by) REFERENCES public.users(id);


--
-- Name: inventory_movements inventory_movements_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory_movements
    ADD CONSTRAINT inventory_movements_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: inventory inventory_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory
    ADD CONSTRAINT inventory_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: inventory inventory_variant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.inventory
    ADD CONSTRAINT inventory_variant_id_fkey FOREIGN KEY (variant_id) REFERENCES public.product_variants(id) ON DELETE CASCADE;


--
-- Name: kb_documents kb_documents_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kb_documents
    ADD CONSTRAINT kb_documents_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: knowledge_embeddings knowledge_embeddings_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_embeddings
    ADD CONSTRAINT knowledge_embeddings_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: macros macros_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.macros
    ADD CONSTRAINT macros_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: media_assets media_assets_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.media_assets
    ADD CONSTRAINT media_assets_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: media_assets media_assets_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.media_assets
    ADD CONSTRAINT media_assets_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.media_assets(id) ON DELETE SET NULL;


--
-- Name: media_assets media_assets_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.media_assets
    ADD CONSTRAINT media_assets_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: messages messages_ai_draft_of_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_ai_draft_of_id_fkey FOREIGN KEY (ai_draft_of_id) REFERENCES public.messages(id);


--
-- Name: messages messages_approved_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_approved_by_fkey FOREIGN KEY (approved_by) REFERENCES public.users(id);


--
-- Name: messages messages_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- Name: messages messages_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: notifications notifications_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: notifications notifications_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: orchestrator_chats orchestrator_chats_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestrator_chats
    ADD CONSTRAINT orchestrator_chats_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.orchestrator_projects(id) ON DELETE SET NULL;


--
-- Name: orchestrator_chats orchestrator_chats_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestrator_chats
    ADD CONSTRAINT orchestrator_chats_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: orchestrator_chats orchestrator_chats_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestrator_chats
    ADD CONSTRAINT orchestrator_chats_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: orchestrator_files orchestrator_files_message_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestrator_files
    ADD CONSTRAINT orchestrator_files_message_id_fkey FOREIGN KEY (message_id) REFERENCES public.orchestrator_messages(id) ON DELETE SET NULL;


--
-- Name: orchestrator_files orchestrator_files_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestrator_files
    ADD CONSTRAINT orchestrator_files_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.orchestrator_projects(id) ON DELETE SET NULL;


--
-- Name: orchestrator_files orchestrator_files_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestrator_files
    ADD CONSTRAINT orchestrator_files_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: orchestrator_files orchestrator_files_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestrator_files
    ADD CONSTRAINT orchestrator_files_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: orchestrator_messages orchestrator_messages_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestrator_messages
    ADD CONSTRAINT orchestrator_messages_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: orchestrator_messages orchestrator_messages_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestrator_messages
    ADD CONSTRAINT orchestrator_messages_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: orchestrator_plans orchestrator_plans_approved_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestrator_plans
    ADD CONSTRAINT orchestrator_plans_approved_by_fkey FOREIGN KEY (approved_by) REFERENCES public.users(id);


--
-- Name: orchestrator_plans orchestrator_plans_rejected_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestrator_plans
    ADD CONSTRAINT orchestrator_plans_rejected_by_fkey FOREIGN KEY (rejected_by) REFERENCES public.users(id);


--
-- Name: orchestrator_plans orchestrator_plans_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestrator_plans
    ADD CONSTRAINT orchestrator_plans_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: orchestrator_plans orchestrator_plans_triggering_message_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestrator_plans
    ADD CONSTRAINT orchestrator_plans_triggering_message_id_fkey FOREIGN KEY (triggering_message_id) REFERENCES public.orchestrator_messages(id) ON DELETE SET NULL;


--
-- Name: orchestrator_projects orchestrator_projects_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestrator_projects
    ADD CONSTRAINT orchestrator_projects_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: orchestrator_projects orchestrator_projects_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orchestrator_projects
    ADD CONSTRAINT orchestrator_projects_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: order_items order_items_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE CASCADE;


--
-- Name: order_items order_items_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: order_items order_items_variant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_variant_id_fkey FOREIGN KEY (variant_id) REFERENCES public.product_variants(id) ON DELETE SET NULL;


--
-- Name: orders orders_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE SET NULL;


--
-- Name: orders orders_shipping_policy_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_shipping_policy_id_fkey FOREIGN KEY (shipping_policy_id) REFERENCES public.shipping_policies(id) ON DELETE SET NULL;


--
-- Name: orders orders_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: organic_contents organic_contents_approved_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organic_contents
    ADD CONSTRAINT organic_contents_approved_by_fkey FOREIGN KEY (approved_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: organic_contents organic_contents_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organic_contents
    ADD CONSTRAINT organic_contents_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: organic_contents organic_contents_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organic_contents
    ADD CONSTRAINT organic_contents_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: password_reset_tokens password_reset_tokens_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: platform_admins platform_admins_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_admins
    ADD CONSTRAINT platform_admins_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: platform_settings platform_settings_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_settings
    ADD CONSTRAINT platform_settings_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: policies policies_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policies
    ADD CONSTRAINT policies_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: pricing_rules pricing_rules_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pricing_rules
    ADD CONSTRAINT pricing_rules_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: pricing_rules pricing_rules_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pricing_rules
    ADD CONSTRAINT pricing_rules_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: product_categories product_categories_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_categories
    ADD CONSTRAINT product_categories_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.product_categories(id) ON DELETE SET NULL;


--
-- Name: product_categories product_categories_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_categories
    ADD CONSTRAINT product_categories_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: product_variants product_variants_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_variants
    ADD CONSTRAINT product_variants_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id) ON DELETE CASCADE;


--
-- Name: product_variants product_variants_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.product_variants
    ADD CONSTRAINT product_variants_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: products products_category_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.product_categories(id) ON DELETE SET NULL;


--
-- Name: products products_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: products products_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: products products_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: rate_limit_buckets rate_limit_buckets_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rate_limit_buckets
    ADD CONSTRAINT rate_limit_buckets_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: refresh_tokens refresh_tokens_replaced_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_replaced_by_fkey FOREIGN KEY (replaced_by) REFERENCES public.refresh_tokens(id);


--
-- Name: refresh_tokens refresh_tokens_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: refresh_tokens refresh_tokens_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refresh_tokens
    ADD CONSTRAINT refresh_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: role_permissions role_permissions_permission_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_permission_id_fkey FOREIGN KEY (permission_id) REFERENCES public.permissions(id) ON DELETE CASCADE;


--
-- Name: role_permissions role_permissions_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE CASCADE;


--
-- Name: roles roles_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: scheduled_posts scheduled_posts_content_asset_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheduled_posts
    ADD CONSTRAINT scheduled_posts_content_asset_id_fkey FOREIGN KEY (content_asset_id) REFERENCES public.content_assets(id) ON DELETE CASCADE;


--
-- Name: scheduled_posts scheduled_posts_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheduled_posts
    ADD CONSTRAINT scheduled_posts_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: scheduled_posts scheduled_posts_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheduled_posts
    ADD CONSTRAINT scheduled_posts_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: shipping_policies shipping_policies_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shipping_policies
    ADD CONSTRAINT shipping_policies_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: shipping_policies shipping_policies_zone_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shipping_policies
    ADD CONSTRAINT shipping_policies_zone_id_fkey FOREIGN KEY (zone_id) REFERENCES public.shipping_zones(id) ON DELETE CASCADE;


--
-- Name: shipping_zones shipping_zones_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.shipping_zones
    ADD CONSTRAINT shipping_zones_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: usage_metrics usage_metrics_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.usage_metrics
    ADD CONSTRAINT usage_metrics_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: user_roles user_roles_assigned_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_assigned_by_fkey FOREIGN KEY (assigned_by) REFERENCES public.users(id);


--
-- Name: user_roles user_roles_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE CASCADE;


--
-- Name: user_roles user_roles_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: user_roles user_roles_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: users users_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: webhook_events webhook_events_integration_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.webhook_events
    ADD CONSTRAINT webhook_events_integration_id_fkey FOREIGN KEY (integration_id) REFERENCES public.integrations(id) ON DELETE SET NULL;


--
-- Name: webhook_events webhook_events_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.webhook_events
    ADD CONSTRAINT webhook_events_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: workflow_runs workflow_runs_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_runs
    ADD CONSTRAINT workflow_runs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: workflow_runs workflow_runs_workflow_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflow_runs
    ADD CONSTRAINT workflow_runs_workflow_id_fkey FOREIGN KEY (workflow_id) REFERENCES public.workflows(id) ON DELETE CASCADE;


--
-- Name: workflows workflows_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflows
    ADD CONSTRAINT workflows_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: workflows workflows_previous_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflows
    ADD CONSTRAINT workflows_previous_version_id_fkey FOREIGN KEY (previous_version_id) REFERENCES public.workflows(id);


--
-- Name: workflows workflows_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.workflows
    ADD CONSTRAINT workflows_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: campaigns; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.campaigns ENABLE ROW LEVEL SECURITY;

--
-- Name: content_assets; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.content_assets ENABLE ROW LEVEL SECURITY;

--
-- Name: conversations; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;

--
-- Name: customers; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.customers ENABLE ROW LEVEL SECURITY;

--
-- Name: integrations; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.integrations ENABLE ROW LEVEL SECURITY;

--
-- Name: orders; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY;

--
-- Name: products; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.products ENABLE ROW LEVEL SECURITY;

--
-- Name: campaigns tenant_isolation_campaigns; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation_campaigns ON public.campaigns USING ((tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid));


--
-- Name: content_assets tenant_isolation_content_assets; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation_content_assets ON public.content_assets USING ((tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid));


--
-- Name: conversations tenant_isolation_conversations; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation_conversations ON public.conversations USING ((tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid));


--
-- Name: customers tenant_isolation_customers; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation_customers ON public.customers USING ((tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid));


--
-- Name: integrations tenant_isolation_integrations; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation_integrations ON public.integrations USING ((tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid));


--
-- Name: orders tenant_isolation_orders; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation_orders ON public.orders USING ((tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid));


--
-- Name: products tenant_isolation_products; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation_products ON public.products USING ((tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid));


--
-- Name: users tenant_isolation_users; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation_users ON public.users USING ((tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid));


--
-- Name: workflows tenant_isolation_workflows; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY tenant_isolation_workflows ON public.workflows USING ((tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid));


--
-- Name: users; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

--
-- Name: workflows; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.workflows ENABLE ROW LEVEL SECURITY;

--
-- PostgreSQL database dump complete
--

\unrestrict CpXoa5aAAEuZm95L6zwCA3TpBzORvKAL39ZUf4Y71X5ZQ3ArsdNGfGlHyddbn3u

