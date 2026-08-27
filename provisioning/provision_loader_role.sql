-- Run this as a role with sufficient privileges (e.g. SECURITYADMIN for the
-- role/user, SYSADMIN for the grants on ftb.gold — or ACCOUNTADMIN for both).
--
-- Creates a dedicated service user + role for loading CSVs into ftb.gold,
-- kept separate from power_bi_svc_user / power_bi_reader_role so the
-- reporting credential stays read-only.

CREATE ROLE IF NOT EXISTS ftb_loader_role;

CREATE USER IF NOT EXISTS ftb_loader_svc_user
  RSA_PUBLIC_KEY = 'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAs3ACBj++yacMRKkN0QL2HRidFtFnWGV6sofAg5F2tneMeTZcbHcSgw2XIu2wHuz8HXv4BCFyORItWcJhXrzulrZUde71gKeXyNVqboc6W2y9jZRseBu2+5PGxHxRuT+vM1Cx9fhMrYxoQl9Bmm1KUah84AWld67f8A5GeQOeVyupWCUs3QVOuRMWDF/zjAf28GEmhEW+k6vDiUCkfXFMk+AgP2eX0rZrbu/kiBSnCM31XxzMZTDJyEKDpaUILkqTuUs5CKh1i3yM1CwsqVj7xH3Sab49K6DEItcbEU49nlovHXBDxS64/CQh16990feEGD1MoVfePK1mnocsIxlbjQIDAQAB'
  DEFAULT_ROLE = ftb_loader_role
  DEFAULT_WAREHOUSE = power_bi_wh
  TYPE = SERVICE
  COMMENT = 'Service account for loading dashboard-inputs CSVs into ftb.gold';

GRANT ROLE ftb_loader_role TO USER ftb_loader_svc_user;
-- So an interactive admin can also see/manage the objects this role creates.
GRANT ROLE ftb_loader_role TO ROLE SYSADMIN;

GRANT USAGE ON WAREHOUSE power_bi_wh TO ROLE ftb_loader_role;

GRANT USAGE ON DATABASE ftb TO ROLE ftb_loader_role;
GRANT USAGE ON SCHEMA ftb.gold TO ROLE ftb_loader_role;
GRANT CREATE TABLE ON SCHEMA ftb.gold TO ROLE ftb_loader_role;
GRANT CREATE STAGE ON SCHEMA ftb.gold TO ROLE ftb_loader_role;

-- Covers reloads of tables this role already created, and tables it will
-- create in the future.
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA ftb.gold TO ROLE ftb_loader_role;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON FUTURE TABLES IN SCHEMA ftb.gold TO ROLE ftb_loader_role;
