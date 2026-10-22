-- =============================================================
-- JobTracker 数据库初始化脚本
-- 用法（root 身份执行）：
--   mysql -h 127.0.0.1 -P 3306 -u root -p < scripts/create_db.sql
-- 说明：
--   1) 应用不直接使用 root，专用账号 jt 仅被授权访问 jobtracker.*
--   2) 字符集显式指定 utf8mb4 / utf8mb4_unicode_ci，避免 8.0/9.x 默认排序规则差异
-- =============================================================

CREATE DATABASE IF NOT EXISTS jobtracker
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- 专用应用账号（MySQL 9 默认 caching_sha2_password，PyMySQL 需安装 cryptography）
-- ⚠️ 执行前请把下面的 __CHANGE_ME__ 替换为你自己的密码，并同步写入 .env 的 DB_PASSWORD
--    真实密码请勿提交到版本库
CREATE USER IF NOT EXISTS 'jt'@'localhost' IDENTIFIED BY '__CHANGE_ME__';
CREATE USER IF NOT EXISTS 'jt'@'127.0.0.1' IDENTIFIED BY '__CHANGE_ME__';

ALTER USER 'jt'@'localhost' IDENTIFIED BY '__CHANGE_ME__';
ALTER USER 'jt'@'127.0.0.1' IDENTIFIED BY '__CHANGE_ME__';

-- 最小权限：只给 jobtracker 库的增删改查与建表权限（Alembic 迁移需要 DDL）
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES, DROP
  ON jobtracker.* TO 'jt'@'localhost';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES, DROP
  ON jobtracker.* TO 'jt'@'127.0.0.1';

FLUSH PRIVILEGES;

SELECT 'jobtracker 数据库与 jt 账号创建完成' AS result;
