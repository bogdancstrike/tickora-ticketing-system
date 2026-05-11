-- Tickora development seed and hardening helper.
--
-- This file is intentionally idempotent. It can bootstrap the admin-facing
-- reference tables in an empty PostgreSQL database, or safely enrich a database
-- already created through Alembic migrations. The full production schema is
-- still owned by migrations/; this script is for local demos, smoke tests, and
-- DBA review of the most important seed/reference rows and hot-path indexes.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    keycloak_subject varchar(255) UNIQUE NOT NULL,
    username varchar(255),
    email varchar(255),
    first_name varchar(255),
    last_name varchar(255),
    user_type varchar(50) NOT NULL DEFAULT 'internal',
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sectors (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code varchar(50) UNIQUE NOT NULL,
    name varchar(255) NOT NULL,
    description text,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sector_memberships (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id),
    sector_id uuid NOT NULL REFERENCES sectors(id),
    membership_role varchar(50) NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_sector_membership UNIQUE (user_id, sector_id, membership_role)
);

CREATE TABLE IF NOT EXISTS metadata_key_definitions (
    key varchar(100) PRIMARY KEY,
    label varchar(255) NOT NULL,
    value_type varchar(20) NOT NULL DEFAULT 'string',
    options jsonb,
    description text,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_sector_memberships_user ON sector_memberships(user_id);
CREATE INDEX IF NOT EXISTS idx_sector_memberships_sector ON sector_memberships(sector_id);
CREATE INDEX IF NOT EXISTS idx_sector_memberships_active_sector_role_user
    ON sector_memberships(sector_id, membership_role, user_id)
    WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_metadata_key_definitions_active
    ON metadata_key_definitions(is_active, key);
INSERT INTO sectors (code, name, description) VALUES
    ('s1',  'Service Desk',        'Frontline intake and common service requests'),
    ('s2',  'Network Operations',  'Network, VPN, connectivity, and firewall incidents'),
    ('s3',  'Infrastructure',      'Servers, storage, virtualization, and operating systems'),
    ('s4',  'Applications',        'Business applications and integrations'),
    ('s5',  'Security',            'Identity, endpoint security, and incident response'),
    ('s6',  'Database Administration', 'Database maintenance and performance optimization'),
    ('s7',  'Cloud Services',      'Cloud infrastructure management and deployment'),
    ('s8',  'DevOps & CI/CD',      'Automation pipelines and developer experience'),
    ('s9',  'Quality Assurance',   'Testing frameworks and quality control'),
    ('s10', 'Field Operations',    'On-site and field support work')
ON CONFLICT (code) DO UPDATE
SET name = EXCLUDED.name,
    description = EXCLUDED.description,
    is_active = true,
    updated_at = now();

CREATE TABLE IF NOT EXISTS categories (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code varchar(50) UNIQUE NOT NULL,
    name varchar(255) NOT NULL,
    description text,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS subcategories (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    category_id uuid NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    code varchar(50) NOT NULL,
    name varchar(255) NOT NULL,
    description text,
    display_order integer NOT NULL DEFAULT 0,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_subcategory_code UNIQUE (category_id, code)
);

CREATE INDEX IF NOT EXISTS idx_categories_code ON categories(code);
CREATE INDEX IF NOT EXISTS idx_subcategories_category ON subcategories(category_id);

INSERT INTO categories (code, name) VALUES
    ('infra', 'Infrastructure'),
    ('apps', 'Applications'),
    ('security', 'Security')
ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, updated_at = now();

INSERT INTO subcategories (category_id, code, name)
SELECT c.id, s.code, s.name
FROM (VALUES
    ('infra', 'network', 'Network Connectivity'),
    ('infra', 'hardware', 'Hardware Failure'),
    ('infra', 'datacenter', 'Datacenter Access'),
    ('apps', 'bug', 'Software Bug'),
    ('apps', 'access', 'Access Request'),
    ('apps', 'feature', 'Feature Request'),
    ('security', 'incident', 'Security Incident'),
    ('security', 'audit', 'Audit Request')
) AS s(cat_code, code, name)
JOIN categories c ON c.code = s.cat_code
ON CONFLICT (category_id, code) DO UPDATE SET name = EXCLUDED.name, updated_at = now();

INSERT INTO users (keycloak_subject, username, email, first_name, last_name, user_type) VALUES
    ('00000000-0000-0000-0000-000000000001', 'admin',       'admin@tickora.local',       'Ana',    'Admin',       'internal'),
    ('00000000-0000-0000-0000-000000000002', 'auditor',     'auditor@tickora.local',     'Alex',   'Auditor',     'internal'),
    ('00000000-0000-0000-0000-000000000003', 'distributor', 'distributor@tickora.local', 'Daria',  'Distributor', 'internal'),
    ('00000000-0000-0000-0000-000000000004', 'chief.s10',   'chief.s10@tickora.local',   'Mihai',  'Chief',       'internal'),
    ('00000000-0000-0000-0000-000000000005', 'member.s10',  'member.s10@tickora.local',  'Ioana',  'Member',      'internal'),
    ('00000000-0000-0000-0000-000000000006', 'member.s2',   'member.s2@tickora.local',   'Radu',   'Network',     'internal'),
    ('00000000-0000-0000-0000-000000000007', 'beneficiary', 'beneficiary@tickora.local', 'Bianca', 'Beneficiary', 'internal'),
    ('00000000-0000-0000-0000-000000000008', 'ben.int.1',   'ben.int.1@tickora.local',   'Ion',    'Vasile',      'internal'),
    ('00000000-0000-0000-0000-000000000009', 'ben.int.2',   'ben.int.2@tickora.local',   'Maria',  'Ionescu',     'internal'),
    ('00000000-0000-0000-0000-000000000010', 'external.user', 'external.user@example.test', 'Eric', 'External', 'external'),
    ('00000000-0000-0000-0000-000000000011', 'ben.ext.1',   'ben.ext.1@example.test',    'George', 'Popescu',     'external'),
    ('00000000-0000-0000-0000-000000000012', 'ben.ext.2',   'ben.ext.2@example.test',    'Elena',  'Radu',        'external')
ON CONFLICT (keycloak_subject) DO UPDATE
SET username = EXCLUDED.username,
    email = EXCLUDED.email,
    first_name = EXCLUDED.first_name,
    last_name = EXCLUDED.last_name,
    user_type = EXCLUDED.user_type,
    is_active = true,
    updated_at = now();

INSERT INTO sector_memberships (user_id, sector_id, membership_role)
SELECT u.id, s.id, role
FROM (VALUES
    ('chief.s10',  's10', 'chief'),
    ('member.s10', 's10', 'member'),
    ('member.s2',  's2',  'member')
) AS seed(username, sector_code, role)
JOIN users u ON u.username = seed.username
JOIN sectors s ON s.code = seed.sector_code
ON CONFLICT (user_id, sector_id, membership_role) DO UPDATE
SET is_active = true,
    updated_at = now();

INSERT INTO metadata_key_definitions (key, label, value_type, options, description) VALUES
    ('importance',   'Importance Level', 'enum',   '["1","2","3","4","5"]'::jsonb, '1 = trivial, 5 = mission critical'),
    ('impact_range', 'Impact Range',     'enum',   '["individual","team","department","organization"]'::jsonb, NULL),
    ('platform',     'Target Platform',  'enum',   '["web","mobile","desktop","backend","infrastructure"]'::jsonb, NULL),
    ('environment',  'Environment',      'enum',   '["production","staging","development","test"]'::jsonb, NULL),
    ('customer_id',  'Customer ID',      'string', NULL, 'External customer or account reference'),
    ('order_ref',    'Order Reference',  'string', NULL, NULL),
    ('expected_at',  'Expected by',      'string', NULL, 'Free-text date or expectation note')
ON CONFLICT (key) DO UPDATE
SET label = EXCLUDED.label,
    value_type = EXCLUDED.value_type,
    options = EXCLUDED.options,
    description = EXCLUDED.description,
    is_active = true,
    updated_at = now();
