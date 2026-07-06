--
-- PostgreSQL database dump
--

\restrict GnQRFkzmQhFv6kETgd7fx88eCESB1IdFRrJe1BPoRrp15hIAcwekcoe62M7FHbd

-- Dumped from database version 16.14 (Ubuntu 16.14-0ubuntu0.24.04.1)
-- Dumped by pg_dump version 16.14 (Ubuntu 16.14-0ubuntu0.24.04.1)

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

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: authors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.authors (
    id integer NOT NULL,
    username text NOT NULL,
    name text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    password_hash text
);


--
-- Name: authors_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.authors_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: authors_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.authors_id_seq OWNED BY public.authors.id;


--
-- Name: extractions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.extractions (
    id integer NOT NULL,
    mode text DEFAULT 'batch'::text NOT NULL,
    anthropic_batch_id text,
    classe smallint NOT NULL,
    pdf_stem text NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    ended_at timestamp with time zone,
    status text DEFAULT 'pending'::text NOT NULL,
    page_range text,
    nb_entries integer DEFAULT 0,
    nb_succeeded integer DEFAULT 0,
    nb_errored integer DEFAULT 0,
    input_tokens bigint DEFAULT 0,
    output_tokens bigint DEFAULT 0,
    cache_write_tokens bigint DEFAULT 0,
    cache_read_tokens bigint DEFAULT 0,
    cost_eur numeric(10,6) DEFAULT 0,
    api_key_hint text
);


--
-- Name: extractions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.extractions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: extractions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.extractions_id_seq OWNED BY public.extractions.id;


--
-- Name: pages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pages (
    id integer NOT NULL,
    class smallint NOT NULL,
    page smallint NOT NULL,
    extraction_id integer,
    image_path text,
    file_size_kb integer,
    text text,
    nb_entries smallint,
    processed_at timestamp with time zone
);


--
-- Name: pages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pages_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pages_id_seq OWNED BY public.pages.id;


--
-- Name: pensionnaires; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pensionnaires (
    id integer NOT NULL,
    class smallint NOT NULL,
    page smallint NOT NULL,
    entry_number smallint,
    x smallint,
    y smallint,
    x_fin smallint,
    y_fin smallint,
    last_name text DEFAULT ''::text NOT NULL,
    particule text,
    first_name text,
    aliases jsonb DEFAULT '[]'::jsonb NOT NULL,
    widow_of text,
    current_spouse_of text,
    title text,
    sex text,
    age smallint,
    birth_year smallint,
    total_amount integer,
    incoherence boolean,
    jobs jsonb DEFAULT '[]'::jsonb NOT NULL,
    detailed_pensions jsonb DEFAULT '[]'::jsonb NOT NULL,
    suggestions jsonb DEFAULT '[]'::jsonb NOT NULL,
    input_tokens integer DEFAULT 0,
    output_tokens integer DEFAULT 0,
    cache_write_tokens integer DEFAULT 0,
    cache_read_tokens integer DEFAULT 0,
    cost_eur numeric(10,6) DEFAULT 0,
    entry_hash text NOT NULL,
    extracted_at timestamp with time zone DEFAULT now(),
    wikidata_id text,
    wikidata_score real,
    prosocour_id text,
    prosocour_score real,
    validation_date timestamp with time zone,
    validation_author_id integer,
    identity_text text,
    rejected_at timestamp with time zone,
    rejected_by integer,
    suggestions_hidden jsonb DEFAULT '[]'::jsonb NOT NULL,
    uid uuid DEFAULT gen_random_uuid() NOT NULL,
    maiden_name text,
    nobiliary_title text,
    observations text
);


--
-- Name: pensionnaires_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pensionnaires_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pensionnaires_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pensionnaires_id_seq OWNED BY public.pensionnaires.id;


--
-- Name: requetes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.requetes (
    id integer NOT NULL,
    title text NOT NULL,
    request text NOT NULL,
    author_id integer
);


--
-- Name: requetes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.requetes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: requetes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.requetes_id_seq OWNED BY public.requetes.id;


--
-- Name: suggestions_archive; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.suggestions_archive (
    id integer NOT NULL,
    entry_hash text NOT NULL,
    round integer NOT NULL,
    suggestions jsonb DEFAULT '[]'::jsonb NOT NULL,
    archived_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: suggestions_archive_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.suggestions_archive_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: suggestions_archive_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.suggestions_archive_id_seq OWNED BY public.suggestions_archive.id;


--
-- Name: authors id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.authors ALTER COLUMN id SET DEFAULT nextval('public.authors_id_seq'::regclass);


--
-- Name: extractions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.extractions ALTER COLUMN id SET DEFAULT nextval('public.extractions_id_seq'::regclass);


--
-- Name: pages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pages ALTER COLUMN id SET DEFAULT nextval('public.pages_id_seq'::regclass);


--
-- Name: pensionnaires id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pensionnaires ALTER COLUMN id SET DEFAULT nextval('public.pensionnaires_id_seq'::regclass);


--
-- Name: requetes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requetes ALTER COLUMN id SET DEFAULT nextval('public.requetes_id_seq'::regclass);


--
-- Name: suggestions_archive id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suggestions_archive ALTER COLUMN id SET DEFAULT nextval('public.suggestions_archive_id_seq'::regclass);


--
-- Name: authors authors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.authors
    ADD CONSTRAINT authors_pkey PRIMARY KEY (id);


--
-- Name: authors authors_username_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.authors
    ADD CONSTRAINT authors_username_key UNIQUE (username);


--
-- Name: extractions extractions_anthropic_batch_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.extractions
    ADD CONSTRAINT extractions_anthropic_batch_id_key UNIQUE (anthropic_batch_id);


--
-- Name: extractions extractions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.extractions
    ADD CONSTRAINT extractions_pkey PRIMARY KEY (id);


--
-- Name: pages pages_class_page_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_class_page_key UNIQUE (class, page);


--
-- Name: pages pages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_pkey PRIMARY KEY (id);


--
-- Name: pensionnaires pensionnaires_entry_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pensionnaires
    ADD CONSTRAINT pensionnaires_entry_hash_key UNIQUE (entry_hash);


--
-- Name: pensionnaires pensionnaires_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pensionnaires
    ADD CONSTRAINT pensionnaires_pkey PRIMARY KEY (id);


--
-- Name: requetes requetes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requetes
    ADD CONSTRAINT requetes_pkey PRIMARY KEY (id);


--
-- Name: suggestions_archive suggestions_archive_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suggestions_archive
    ADD CONSTRAINT suggestions_archive_pkey PRIMARY KEY (id);


--
-- Name: idx_pens_amount; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pens_amount ON public.pensionnaires USING btree (total_amount);


--
-- Name: idx_pens_class; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pens_class ON public.pensionnaires USING btree (class);


--
-- Name: idx_pens_fts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pens_fts ON public.pensionnaires USING gin (to_tsvector('french'::regconfig, ((((COALESCE(last_name, ''::text) || ' '::text) || COALESCE(first_name, ''::text)) || ' '::text) || COALESCE(title, ''::text))));


--
-- Name: idx_pens_jobs; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pens_jobs ON public.pensionnaires USING gin (jobs);


--
-- Name: idx_pens_last_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pens_last_name ON public.pensionnaires USING btree (last_name);


--
-- Name: idx_pens_pensions; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pens_pensions ON public.pensionnaires USING gin (detailed_pensions);


--
-- Name: pensionnaires_uid_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX pensionnaires_uid_idx ON public.pensionnaires USING btree (uid);


--
-- Name: suggestions_archive_entry_hash_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX suggestions_archive_entry_hash_idx ON public.suggestions_archive USING btree (entry_hash);


--
-- Name: pages pages_extraction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_extraction_id_fkey FOREIGN KEY (extraction_id) REFERENCES public.extractions(id);


--
-- Name: pensionnaires pensionnaires_rejected_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pensionnaires
    ADD CONSTRAINT pensionnaires_rejected_by_fkey FOREIGN KEY (rejected_by) REFERENCES public.authors(id);


--
-- Name: pensionnaires pensionnaires_validation_author_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pensionnaires
    ADD CONSTRAINT pensionnaires_validation_author_id_fkey FOREIGN KEY (validation_author_id) REFERENCES public.authors(id);


--
-- Name: requetes requetes_author_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requetes
    ADD CONSTRAINT requetes_author_id_fkey FOREIGN KEY (author_id) REFERENCES public.authors(id);


--
-- PostgreSQL database dump complete
--

\unrestrict GnQRFkzmQhFv6kETgd7fx88eCESB1IdFRrJe1BPoRrp15hIAcwekcoe62M7FHbd

