SET NAMES utf8mb4;

CREATE DATABASE IF NOT EXISTS `device_service`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

GRANT ALL PRIVILEGES ON `device_service`.* TO 'device'@'%';
FLUSH PRIVILEGES;

USE `device_service`;

CREATE TABLE IF NOT EXISTS `customers` (
  `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
  `customer_id` VARCHAR(64) NOT NULL UNIQUE,
  `nickname` VARCHAR(100) NOT NULL,
  `level` VARCHAR(32) NOT NULL,
  `mobile_masked` VARCHAR(32) NOT NULL,
  `created_at` DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `devices` (
  `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
  `device_id` VARCHAR(64) NOT NULL UNIQUE,
  `customer_id` BIGINT NOT NULL,
  `model` VARCHAR(128) NOT NULL,
  `serial_number` VARCHAR(64) NOT NULL,
  `category` VARCHAR(64) NOT NULL,
  `purchase_date` DATETIME NOT NULL,
  `warranty_months` INT NOT NULL,
  `status` VARCHAR(32) NOT NULL,
  `attributes_json` JSON NOT NULL,
  `cover_url` VARCHAR(500) NULL,
  `created_at` DATETIME NOT NULL,
  CONSTRAINT `fk_devices_customer` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `device_histories` (
  `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
  `device_id` BIGINT NOT NULL,
  `event_time` DATETIME NOT NULL,
  `event_type` VARCHAR(64) NOT NULL,
  `event_desc` VARCHAR(255) NOT NULL,
  CONSTRAINT `fk_device_histories_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `service_tickets` (
  `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
  `ticket_id` VARCHAR(64) NOT NULL UNIQUE,
  `device_id` BIGINT NOT NULL,
  `customer_id` BIGINT NOT NULL,
  `problem_type` VARCHAR(64) NOT NULL,
  `problem_desc` TEXT NOT NULL,
  `tried_steps` TEXT NULL,
  `priority` VARCHAR(32) NOT NULL,
  `status` VARCHAR(32) NOT NULL,
  `status_desc` VARCHAR(255) NOT NULL,
  `contact_name` VARCHAR(64) NOT NULL,
  `contact_phone_masked` VARCHAR(32) NOT NULL,
  `contact_address` VARCHAR(255) NOT NULL,
  `created_at` DATETIME NOT NULL,
  `updated_at` DATETIME NOT NULL,
  CONSTRAINT `fk_tickets_device` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`),
  CONSTRAINT `fk_tickets_customer` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `repair_records` (
  `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
  `ticket_id` BIGINT NOT NULL,
  `logistics_company` VARCHAR(64) NOT NULL,
  `tracking_number` VARCHAR(64) NOT NULL,
  `status` VARCHAR(32) NOT NULL,
  `status_desc` VARCHAR(255) NOT NULL,
  `updated_at` DATETIME NOT NULL,
  CONSTRAINT `fk_repair_records_ticket` FOREIGN KEY (`ticket_id`) REFERENCES `service_tickets` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `repair_traces` (
  `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
  `repair_record_id` BIGINT NOT NULL,
  `trace_time` DATETIME NOT NULL,
  `trace_desc` VARCHAR(255) NOT NULL,
  CONSTRAINT `fk_repair_traces_record` FOREIGN KEY (`repair_record_id`) REFERENCES `repair_records` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `human_transfers` (
  `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
  `transfer_id` VARCHAR(64) NOT NULL UNIQUE,
  `ticket_id` BIGINT NULL,
  `customer_id` BIGINT NOT NULL,
  `reason` VARCHAR(255) NOT NULL,
  `status` VARCHAR(32) NOT NULL,
  `status_desc` VARCHAR(255) NOT NULL,
  `created_at` DATETIME NOT NULL,
  CONSTRAINT `fk_transfers_ticket` FOREIGN KEY (`ticket_id`) REFERENCES `service_tickets` (`id`),
  CONSTRAINT `fk_transfers_customer` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── 脱敏种子数据（演示用，非真实企业数据） ──────────────────────────

INSERT INTO `customers` (`customer_id`, `nickname`, `level`, `mobile_masked`, `created_at`) VALUES
  ('u1001', '李工', '企业客户', '138****1234', '2026-01-05 09:00:00'),
  ('u1002', '王敏', '普通客户', '139****5678', '2026-01-08 10:30:00'),
  ('u1003', '陈晨', '企业客户', '137****2468', '2026-01-12 19:20:00');

INSERT INTO `devices` (
  `device_id`, `customer_id`, `model`, `serial_number`, `category`,
  `purchase_date`, `warranty_months`, `status`, `attributes_json`, `cover_url`, `created_at`
) VALUES
  (
    'DEV-2026-0001',
    (SELECT `id` FROM `customers` WHERE `customer_id` = 'u1001'),
    'H3C LA2608',
    'SN-LA2608-001',
    '网络设备',
    '2026-02-15 00:00:00',
    12,
    'in_use',
    JSON_OBJECT('端口数', '8', '无线协议', 'Wi-Fi 6', '管理方式', 'AC统一管理', '安装位置', '上海机房A'),
    'https://placehold.co/400x400/0d9488/ffffff?text=H3C+LA2608',
    '2026-02-15 09:00:00'
  ),
  (
    'DEV-2026-0002',
    (SELECT `id` FROM `customers` WHERE `customer_id` = 'u1002'),
    'RS PRO RS-12',
    'SN-RS12-002',
    '万用表',
    '2024-03-10 00:00:00',
    24,
    'in_use',
    JSON_OBJECT('量程', '自动/手动', '显示', '数字双显', '防护等级', 'CAT III 600V'),
    'https://placehold.co/400x400/f59e0b/ffffff?text=RS+PRO+RS-12',
    '2024-03-10 11:00:00'
  ),
  (
    'DEV-2026-0003',
    (SELECT `id` FROM `customers` WHERE `customer_id` = 'u1003'),
    '华为擎云 L540',
    'SN-L540-003',
    '笔记本',
    '2025-01-20 00:00:00',
    12,
    'in_use',
    JSON_OBJECT('CPU', '麒麟9000C', '内存', '16GB', '硬盘', '512GB SSD', '系统', '统信UOS'),
    'https://placehold.co/400x400/1e3a5f/ffffff?text=Huawei+L540',
    '2025-01-20 14:00:00'
  ),
  (
    'DEV-2026-0004',
    (SELECT `id` FROM `customers` WHERE `customer_id` = 'u1001'),
    'H3C S5130-28S-EI',
    'SN-S5130-004',
    '网络设备',
    '2023-06-01 00:00:00',
    12,
    'in_use',
    JSON_OBJECT('端口数', '28', '交换容量', '336Gbps', '管理方式', 'CLI/Web', '安装位置', '上海机房A'),
    'https://placehold.co/400x400/0d9488/ffffff?text=H3C+S5130',
    '2023-06-01 09:30:00'
  );

INSERT INTO `device_histories` (`device_id`, `event_time`, `event_type`, `event_desc`) VALUES
  (
    (SELECT `id` FROM `devices` WHERE `device_id` = 'DEV-2026-0001'),
    '2026-02-15 09:00:00',
    'install',
    '设备完成安装调试并验收。'
  ),
  (
    (SELECT `id` FROM `devices` WHERE `device_id` = 'DEV-2026-0001'),
    '2026-03-20 15:30:00',
    'config',
    '完成业务 VLAN 与无线控制器地址配置。'
  ),
  (
    (SELECT `id` FROM `devices` WHERE `device_id` = 'DEV-2026-0002'),
    '2024-03-10 11:00:00',
    'install',
    '设备到货并完成首次校准。'
  ),
  (
    (SELECT `id` FROM `devices` WHERE `device_id` = 'DEV-2026-0003'),
    '2025-01-20 14:00:00',
    'install',
    '笔记本完成系统初始化交付。'
  ),
  (
    (SELECT `id` FROM `devices` WHERE `device_id` = 'DEV-2026-0004'),
    '2023-06-01 09:30:00',
    'install',
    '交换机上架并完成堆叠配置。'
  ),
  (
    (SELECT `id` FROM `devices` WHERE `device_id` = 'DEV-2026-0004'),
    '2025-08-12 10:00:00',
    'repair',
    '电源模块更换完成，恢复正常。'
  );

INSERT INTO `service_tickets` (
  `ticket_id`, `device_id`, `customer_id`, `problem_type`, `problem_desc`, `tried_steps`,
  `priority`, `status`, `status_desc`, `contact_name`, `contact_phone_masked`, `contact_address`,
  `created_at`, `updated_at`
) VALUES
  (
    'TKT-2026-000001',
    (SELECT `id` FROM `devices` WHERE `device_id` = 'DEV-2026-0001'),
    (SELECT `id` FROM `customers` WHERE `customer_id` = 'u1001'),
    'controller_connection',
    'LA2608 无法连接无线控制器，AP 无法上线。',
    '已重启设备；已检查网线；已确认 AC 地址配置。',
    'high',
    'repairing',
    '设备已寄修，维修中心处理中。',
    '李先生',
    '138****1234',
    '上海市浦东新区世纪大道 100 号',
    '2026-04-10 10:00:00',
    '2026-04-12 09:00:00'
  ),
  (
    'TKT-2026-000002',
    (SELECT `id` FROM `devices` WHERE `device_id` = 'DEV-2026-0003'),
    (SELECT `id` FROM `customers` WHERE `customer_id` = 'u1003'),
    'power_on',
    '笔记本无法开机，电源指示灯不亮。',
    '已更换电源适配器测试；已长按电源键 15 秒放电。',
    'urgent',
    'submitted',
    '工单已创建，等待受理。',
    '陈先生',
    '137****2468',
    '北京市朝阳区建国路 56 号',
    '2026-04-15 14:20:00',
    '2026-04-15 14:20:00'
  ),
  (
    'TKT-2026-000003',
    (SELECT `id` FROM `devices` WHERE `device_id` = 'DEV-2026-0002'),
    (SELECT `id` FROM `customers` WHERE `customer_id` = 'u1002'),
    'measurement_error',
    '万用表电阻档读数漂移严重。',
    '已更换表笔；已做简易校准。',
    'normal',
    'completed',
    '维修完成，设备已寄回。',
    '王女士',
    '139****5678',
    '杭州市西湖区文三路 88 号',
    '2026-03-01 09:15:00',
    '2026-03-18 16:40:00'
  );

INSERT INTO `repair_records` (
  `ticket_id`, `logistics_company`, `tracking_number`, `status`, `status_desc`, `updated_at`
) VALUES
  (
    (SELECT `id` FROM `service_tickets` WHERE `ticket_id` = 'TKT-2026-000001'),
    '顺丰速运',
    'SF-REPAIR-0001',
    '维修中',
    '设备已到达维修中心，工程师处理中。',
    '2026-04-12 09:00:00'
  ),
  (
    (SELECT `id` FROM `service_tickets` WHERE `ticket_id` = 'TKT-2026-000003'),
    '京东物流',
    'JD-REPAIR-0003',
    '已签收',
    '设备已寄回并签收。',
    '2026-03-18 16:40:00'
  );

INSERT INTO `repair_traces` (`repair_record_id`, `trace_time`, `trace_desc`) VALUES
  (
    (SELECT `id` FROM `repair_records` WHERE `tracking_number` = 'SF-REPAIR-0001'),
    '2026-04-12 09:00:00',
    '设备已到达维修中心，工程师处理中。'
  ),
  (
    (SELECT `id` FROM `repair_records` WHERE `tracking_number` = 'SF-REPAIR-0001'),
    '2026-04-11 15:20:00',
    '顺丰已揽收寄修设备。'
  ),
  (
    (SELECT `id` FROM `repair_records` WHERE `tracking_number` = 'SF-REPAIR-0001'),
    '2026-04-10 18:00:00',
    '用户确认寄修，等待上门取件。'
  ),
  (
    (SELECT `id` FROM `repair_records` WHERE `tracking_number` = 'JD-REPAIR-0003'),
    '2026-03-18 16:40:00',
    '设备已寄回并签收。'
  ),
  (
    (SELECT `id` FROM `repair_records` WHERE `tracking_number` = 'JD-REPAIR-0003'),
    '2026-03-12 10:00:00',
    '校准完成，准备寄出。'
  ),
  (
    (SELECT `id` FROM `repair_records` WHERE `tracking_number` = 'JD-REPAIR-0003'),
    '2026-03-03 11:00:00',
    '设备到达维修中心。'
  );

INSERT INTO `human_transfers` (
  `transfer_id`, `ticket_id`, `customer_id`, `reason`, `status`, `status_desc`, `created_at`
) VALUES
  (
    'HUM-202604100001',
    (SELECT `id` FROM `service_tickets` WHERE `ticket_id` = 'TKT-2026-000001'),
    (SELECT `id` FROM `customers` WHERE `customer_id` = 'u1001'),
    '用户对排查结果不满意，要求人工跟进',
    'transferred',
    '已转接人工客服，请稍候。',
    '2026-04-10 11:30:00'
  );
