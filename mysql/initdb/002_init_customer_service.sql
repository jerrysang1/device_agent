SET NAMES utf8mb4;

CREATE DATABASE IF NOT EXISTS `customer_service`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

GRANT ALL PRIVILEGES ON `customer_service`.* TO 'device'@'%';
FLUSH PRIVILEGES;

USE `customer_service`;

-- 对话状态存储（DeviceCare Agent 的 DialogueState 持久化预留）
CREATE TABLE IF NOT EXISTS `dialogue_states` (
  `sender_id` VARCHAR(255) NOT NULL COMMENT '用户唯一标识',
  `state_json` TEXT NOT NULL COMMENT '完整对话状态 JSON（active_task/paused_tasks/focused_device/pending_confirmation）',
  `updated_at` DATETIME NULL,
  PRIMARY KEY (`sender_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Agent 执行审计（路由、工具、校验结果等，便于评测与观测）
CREATE TABLE IF NOT EXISTS `agent_traces` (
  `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
  `sender_id` VARCHAR(255) NOT NULL,
  `session_id` VARCHAR(64) NULL,
  `turn_index` INT NOT NULL,
  `route` VARCHAR(32) NOT NULL,
  `intent` VARCHAR(64) NULL,
  `tool_name` VARCHAR(64) NULL,
  `tool_ok` TINYINT(1) NULL,
  `latency_ms` INT NULL,
  `payload_json` JSON NULL,
  `created_at` DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
