-- Run in a MySQL administrator session. Use MySQL 8.0.16+ or 8.4 with InnoDB.
-- Create an application user separately with a strong password; never use root
-- as the web application's account. Do not commit real credentials.
CREATE DATABASE IF NOT EXISTS animal_shelter
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- After setting DATABASE_URL, flask --app shelter init-db creates the tables.
-- This is initial schema creation, not a schema migration system.
