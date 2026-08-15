-- Run this as a role with sufficient privileges (e.g. SYSADMIN or ACCOUNTADMIN).
--
-- Extends ftb_loader_role (see provision_loader_role.sql) with access to
-- ftb.bronze, so it can create tables and read from the existing S3 stage
-- there for the one-time Ceres parquet historical load.

GRANT USAGE ON SCHEMA ftb.bronze TO ROLE ftb_loader_role;
GRANT CREATE TABLE ON SCHEMA ftb.bronze TO ROLE ftb_loader_role;
-- The existing s3_stage is scoped to s3://.../raw/mmg, not the bucket root,
-- so it can't see files under raw/ceres/. ftb_loader_role creates its own
-- stage (same storage integration, different URL) rather than widening an
-- existing stage other pipelines depend on.
GRANT CREATE STAGE ON SCHEMA ftb.bronze TO ROLE ftb_loader_role;
GRANT CREATE FILE FORMAT ON SCHEMA ftb.bronze TO ROLE ftb_loader_role;
-- Needed to create a stage that uses this integration (account-level grant).
GRANT USAGE ON INTEGRATION s3_snowflakestaging1 TO ROLE ftb_loader_role;

-- Read access to whatever the existing S3 stage(s) are named in bronze
-- (matches the pattern your teammate used, e.g. ftb.bronze.s3_stage).
GRANT USAGE, READ ON ALL STAGES IN SCHEMA ftb.bronze TO ROLE ftb_loader_role;
GRANT USAGE, READ ON FUTURE STAGES IN SCHEMA ftb.bronze TO ROLE ftb_loader_role;

-- Read access to any existing file formats (e.g. a PARQUET format) in bronze.
GRANT USAGE ON ALL FILE FORMATS IN SCHEMA ftb.bronze TO ROLE ftb_loader_role;
GRANT USAGE ON FUTURE FILE FORMATS IN SCHEMA ftb.bronze TO ROLE ftb_loader_role;

-- DML on the tables this role creates during the load (and any future ones).
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA ftb.bronze TO ROLE ftb_loader_role;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON FUTURE TABLES IN SCHEMA ftb.bronze TO ROLE ftb_loader_role;
