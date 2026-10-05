-- psql variables are safely quoted as SQL literals, then formatted as identifiers.
SELECT format('CREATE ROLE %I LOGIN', 'pokemon_reader')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pokemon_reader') \gexec
SELECT format('CREATE ROLE %I LOGIN', 'pokemon_writer')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pokemon_writer') \gexec
SELECT format('CREATE ROLE %I LOGIN', 'airflow_service')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'airflow_service') \gexec
ALTER ROLE pokemon_reader PASSWORD :'reader_password';
ALTER ROLE pokemon_writer PASSWORD :'writer_password';
ALTER ROLE airflow_service PASSWORD :'airflow_password';
SELECT format('CREATE DATABASE %I OWNER %I', 'airflow_meta', 'airflow_service')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'airflow_meta') \gexec
REVOKE CONNECT ON DATABASE airflow_meta FROM PUBLIC, pokemon_reader, pokemon_writer;
GRANT CONNECT ON DATABASE airflow_meta TO airflow_service;
SELECT format('REVOKE CONNECT ON DATABASE %I FROM PUBLIC, airflow_service', current_database()) \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO pokemon_reader, pokemon_writer', current_database()) \gexec
GRANT USAGE ON SCHEMA public TO pokemon_reader, pokemon_writer;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO pokemon_reader;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO pokemon_writer;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO pokemon_writer;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO pokemon_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO pokemon_writer;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO pokemon_writer;
