"""baseline schema

Fasst die 41 bisherigen Migrationen (Stand v1.5.0) zu einer zusammen.
Erzeugt mit backend/scripts/squash_migrations.sh aus dem Schema, das die
bisherige Migrationskette auf MariaDB erzeugt hat.

Die Revisionsnummer entspricht dem letzten Stand der alten Kette: Bestehende
Datenbanken stehen bereits darauf und bleiben unverändert; eine leere
Datenbank erhält das vollständige Schema in einem Schritt.

Revision ID: e5c7a9b1d3f2
Revises:
"""
from typing import Sequence, Union

from alembic import op


revision: str = "e5c7a9b1d3f2"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SCHEMA = [
    (
        'CREATE TABLE `charging_sessions` (\n'
        '  `id` int(11) NOT NULL AUTO_INCREMENT,\n'
        '  `hager_session_id` varchar(100) DEFAULT NULL,\n'
        '  `station_id` varchar(100) NOT NULL,\n'
        '  `start_time` datetime NOT NULL,\n'
        '  `end_time` datetime NOT NULL,\n'
        '  `rfid_card_id` int(11) DEFAULT NULL,\n'
        '  `energy_total_kwh` float NOT NULL,\n'
        '  `energy_pv_kwh` float NOT NULL,\n'
        '  `cost_grid_net` decimal(10,4) DEFAULT NULL,\n'
        '  `cost_pv_net` decimal(10,4) DEFAULT NULL,\n'
        '  `vat_rate` decimal(5,2) DEFAULT NULL,\n'
        '  `invoiced` tinyint(1) NOT NULL,\n'
        '  `invoice_id` int(11) DEFAULT NULL,\n'
        '  `created_at` datetime NOT NULL,\n'
        '  `updated_at` datetime NOT NULL,\n'
        '  `import_hash` varchar(64) DEFAULT NULL,\n'
        '  `source` varchar(20) NOT NULL,\n'
        '  `rfid_assignment_id` int(11) DEFAULT NULL,\n'
        '  `rfid_number` varchar(32) DEFAULT NULL,\n'
        '  `wallbox_id` varchar(64) DEFAULT NULL,\n'
        '  `discarded_at` datetime DEFAULT NULL,\n'
        '  `discarded_by_user_id` int(11) DEFAULT NULL,\n'
        '  `discard_reason` varchar(255) DEFAULT NULL,\n'
        '  PRIMARY KEY (`id`),\n'
        '  UNIQUE KEY `hager_session_id` (`hager_session_id`),\n'
        '  UNIQUE KEY `import_hash` (`import_hash`),\n'
        '  KEY `rfid_card_id` (`rfid_card_id`),\n'
        '  KEY `ix_charging_sessions_rfid_assignment_id` (`rfid_assignment_id`),\n'
        '  KEY `ix_charging_sessions_rfid_number` (`rfid_number`),\n'
        '  KEY `ix_charging_sessions_wallbox_id` (`wallbox_id`),\n'
        '  KEY `ix_charging_sessions_discarded_at` (`discarded_at`),\n'
        '  KEY `fk_charging_sessions_discarded_by_user_id_users` (`discarded_by_user_id`),\n'
        '  CONSTRAINT `charging_sessions_ibfk_1` FOREIGN KEY (`rfid_card_id`) REFERENCES `rfid_cards` (`id`),\n'
        '  CONSTRAINT `fk_charging_sessions_discarded_by_user_id_users` FOREIGN KEY (`discarded_by_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,\n'
        '  CONSTRAINT `fk_charging_sessions_rfid_assignment_id_rfid_card_assignments` FOREIGN KEY (`rfid_assignment_id`) REFERENCES `rfid_card_assignments` (`id`)\n'
        ') ENGINE=InnoDB'
    ),
    (
        'CREATE TABLE `energy_prices` (\n'
        '  `id` int(11) NOT NULL AUTO_INCREMENT,\n'
        '  `valid_from` datetime NOT NULL,\n'
        '  `grid_price_net` decimal(10,4) NOT NULL,\n'
        '  `pv_price_net` decimal(10,4) NOT NULL,\n'
        '  `vat_rate` decimal(5,2) NOT NULL,\n'
        '  `created_at` datetime NOT NULL,\n'
        '  `updated_at` datetime NOT NULL,\n'
        '  PRIMARY KEY (`id`)\n'
        ') ENGINE=InnoDB'
    ),
    (
        'CREATE TABLE `global_settings` (\n'
        '  `id` int(11) NOT NULL,\n'
        '  `monthly_base_fee_net` decimal(12,4) NOT NULL DEFAULT 0.0000,\n'
        '  `monthly_base_fee_vat_rate` decimal(5,2) NOT NULL DEFAULT 19.00,\n'
        '  `created_at` datetime NOT NULL,\n'
        '  `updated_at` datetime NOT NULL,\n'
        "  `app_name` varchar(255) NOT NULL DEFAULT 'Witty-Accounting',\n"
        '  `invoice_payment_term_days` int(11) NOT NULL DEFAULT 0,\n'
        '  `invoice_issuer_name` varchar(255) DEFAULT NULL,\n'
        '  `invoice_issuer_address` varchar(500) DEFAULT NULL,\n'
        '  `invoice_tax_number` varchar(50) DEFAULT NULL,\n'
        '  `invoice_vat_id` varchar(50) DEFAULT NULL,\n'
        '  `invoice_bank_name` varchar(255) DEFAULT NULL,\n'
        '  `invoice_iban` varchar(34) DEFAULT NULL,\n'
        '  `invoice_bic` varchar(11) DEFAULT NULL,\n'
        "  `invoice_number_prefix` varchar(20) NOT NULL DEFAULT 'RE',\n"
        '  `smtp_use_database_settings` tinyint(1) NOT NULL DEFAULT 0,\n'
        '  `mail_sending_enabled` tinyint(1) NOT NULL DEFAULT 1,\n'
        '  `smtp_host` varchar(255) DEFAULT NULL,\n'
        '  `smtp_port` int(11) DEFAULT NULL,\n'
        '  `smtp_timeout_seconds` decimal(8,2) DEFAULT NULL,\n'
        '  `smtp_starttls` tinyint(1) DEFAULT NULL,\n'
        '  `smtp_username` varchar(255) DEFAULT NULL,\n'
        '  `smtp_password_encrypted` text DEFAULT NULL,\n'
        '  `mail_from_address` varchar(320) DEFAULT NULL,\n'
        '  `mail_from_name` varchar(255) DEFAULT NULL,\n'
        '  `password_min_length` int(11) NOT NULL DEFAULT 8,\n'
        '  `password_require_uppercase` tinyint(1) NOT NULL DEFAULT 1,\n'
        '  `password_require_lowercase` tinyint(1) NOT NULL DEFAULT 1,\n'
        '  `password_require_digit` tinyint(1) NOT NULL DEFAULT 1,\n'
        '  `password_require_special` tinyint(1) NOT NULL DEFAULT 1,\n'
        '  `maintenance_mode` tinyint(1) NOT NULL DEFAULT 0,\n'
        '  `dashboard_note` text DEFAULT NULL,\n'
        "  `invoice_pdf_format` varchar(20) NOT NULL DEFAULT 'standard',\n"
        "  `frontend_base_url` varchar(2048) NOT NULL DEFAULT 'http://localhost:5173',\n"
        '  `password_reset_token_expire_minutes` int(11) NOT NULL DEFAULT 60,\n'
        '  `postal_delivery_fee_net` decimal(12,4) NOT NULL DEFAULT 0.0000,\n'
        '  `mail_smime_enabled` tinyint(1) NOT NULL DEFAULT 0,\n'
        '  `mail_smime_pkcs12_data` blob DEFAULT NULL,\n'
        '  `mail_smime_pkcs12_filename` varchar(255) DEFAULT NULL,\n'
        '  `mail_smime_pkcs12_password_encrypted` text DEFAULT NULL,\n'
        '  `billing_start_date` date DEFAULT NULL,\n'
        '  `invoice_export_sftp_enabled` tinyint(1) NOT NULL DEFAULT 0,\n'
        '  `invoice_export_sftp_host` varchar(255) DEFAULT NULL,\n'
        '  `invoice_export_sftp_port` int(11) NOT NULL DEFAULT 22,\n'
        '  `invoice_export_sftp_username` varchar(255) DEFAULT NULL,\n'
        '  `invoice_export_sftp_directory` varchar(1024) DEFAULT NULL,\n'
        '  `invoice_girocode_enabled` tinyint(1) NOT NULL DEFAULT 0,\n'
        '  `invoice_issuer_phone` varchar(50) DEFAULT NULL,\n'
        '  `hager_username` varchar(320) DEFAULT NULL,\n'
        '  `hager_password_encrypted` text DEFAULT NULL,\n'
        '  `hager_installation_id` varchar(50) DEFAULT NULL,\n'
        '  `hager_auto_import_enabled` tinyint(1) NOT NULL DEFAULT 0,\n'
        '  `hager_auto_import_interval_hours` int(11) NOT NULL DEFAULT 24,\n'
        "  `hager_auto_import_start_time` varchar(5) NOT NULL DEFAULT '03:00',\n"
        '  `hager_auto_import_last_started_at` datetime DEFAULT NULL,\n'
        '  `hager_auto_import_last_finished_at` datetime DEFAULT NULL,\n'
        '  `hager_auto_import_last_status` varchar(20) DEFAULT NULL,\n'
        '  `hager_auto_import_last_message` text DEFAULT NULL,\n'
        '  `hager_last_successful_fetch_at` datetime DEFAULT NULL,\n'
        '  `hager_serial_number` varchar(50) DEFAULT NULL,\n'
        '  `import_skip_empty_sessions` tinyint(1) NOT NULL DEFAULT 0,\n'
        '  `data_timezone` varchar(64) DEFAULT NULL,\n'
        "  `locale` varchar(10) NOT NULL DEFAULT 'de-DE',\n"
        "  `currency` varchar(3) NOT NULL DEFAULT 'EUR',\n"
        "  `default_language` varchar(5) NOT NULL DEFAULT 'de',\n"
        '  PRIMARY KEY (`id`)\n'
        ') ENGINE=InnoDB'
    ),
    (
        'CREATE TABLE `import_state` (\n'
        '  `id` int(11) NOT NULL AUTO_INCREMENT,\n'
        '  `last_successful_import` datetime DEFAULT NULL,\n'
        '  `created_at` datetime NOT NULL,\n'
        '  `updated_at` datetime NOT NULL,\n'
        '  PRIMARY KEY (`id`)\n'
        ') ENGINE=InnoDB'
    ),
    (
        'CREATE TABLE `invoice_items` (\n'
        '  `id` int(11) NOT NULL AUTO_INCREMENT,\n'
        '  `invoice_id` int(11) NOT NULL,\n'
        '  `charging_session_id` int(11) DEFAULT NULL,\n'
        '  `position_number` int(11) NOT NULL,\n'
        '  `description` varchar(500) NOT NULL,\n'
        '  `session_start` datetime DEFAULT NULL,\n'
        '  `session_end` datetime DEFAULT NULL,\n'
        '  `station_id` varchar(255) DEFAULT NULL,\n'
        '  `energy_total_kwh` decimal(12,4) DEFAULT NULL,\n'
        '  `energy_grid_kwh` decimal(12,4) DEFAULT NULL,\n'
        '  `energy_pv_kwh` decimal(12,4) DEFAULT NULL,\n'
        '  `grid_price_net` decimal(10,4) DEFAULT NULL,\n'
        '  `pv_price_net` decimal(10,4) DEFAULT NULL,\n'
        '  `cost_grid_net` decimal(12,4) DEFAULT NULL,\n'
        '  `cost_pv_net` decimal(12,4) DEFAULT NULL,\n'
        '  `net_amount` decimal(12,4) NOT NULL,\n'
        '  `vat_rate` decimal(5,2) NOT NULL,\n'
        '  `vat_amount` decimal(12,2) NOT NULL,\n'
        '  `gross_amount` decimal(12,2) NOT NULL,\n'
        '  `reversed_invoice_item_id` int(11) DEFAULT NULL,\n'
        '  `rebills_invoice_item_id` int(11) DEFAULT NULL,\n'
        "  `item_type` varchar(30) NOT NULL DEFAULT 'charging_session',\n"
        '  `monthly_base_fee_charge_id` int(11) DEFAULT NULL,\n'
        '  PRIMARY KEY (`id`),\n'
        '  UNIQUE KEY `uq_invoice_items_invoice_position` (`invoice_id`,`position_number`),\n'
        '  UNIQUE KEY `reversed_invoice_item_id` (`reversed_invoice_item_id`),\n'
        '  UNIQUE KEY `uq_invoice_items_rebills_invoice_item_id` (`rebills_invoice_item_id`),\n'
        '  KEY `ix_invoice_items_invoice_id` (`invoice_id`),\n'
        '  KEY `ix_invoice_items_charging_session_id` (`charging_session_id`),\n'
        '  KEY `ix_invoice_items_monthly_base_fee_charge_id` (`monthly_base_fee_charge_id`),\n'
        '  CONSTRAINT `fk_invoice_items_monthly_base_fee_charge` FOREIGN KEY (`monthly_base_fee_charge_id`) REFERENCES `monthly_base_fee_charges` (`id`),\n'
        '  CONSTRAINT `fk_invoice_items_rebills_invoice_item_id_invoice_items` FOREIGN KEY (`rebills_invoice_item_id`) REFERENCES `invoice_items` (`id`),\n'
        '  CONSTRAINT `invoice_items_ibfk_1` FOREIGN KEY (`charging_session_id`) REFERENCES `charging_sessions` (`id`),\n'
        '  CONSTRAINT `invoice_items_ibfk_2` FOREIGN KEY (`invoice_id`) REFERENCES `invoices` (`id`) ON DELETE CASCADE,\n'
        '  CONSTRAINT `invoice_items_ibfk_3` FOREIGN KEY (`reversed_invoice_item_id`) REFERENCES `invoice_items` (`id`)\n'
        ') ENGINE=InnoDB'
    ),
    (
        'CREATE TABLE `invoices` (\n'
        '  `id` int(11) NOT NULL AUTO_INCREMENT,\n'
        '  `invoice_number` varchar(50) DEFAULT NULL,\n'
        '  `user_id` int(11) NOT NULL,\n'
        "  `status` varchar(20) NOT NULL DEFAULT 'draft',\n"
        '  `issue_date` date DEFAULT NULL,\n'
        '  `service_period_start` datetime NOT NULL,\n'
        '  `service_period_end` datetime NOT NULL,\n'
        "  `currency` varchar(3) NOT NULL DEFAULT 'EUR',\n"
        '  `total_net` decimal(12,2) NOT NULL DEFAULT 0.00,\n'
        '  `vat_amount` decimal(12,2) NOT NULL DEFAULT 0.00,\n'
        '  `total_gross` decimal(12,2) NOT NULL DEFAULT 0.00,\n'
        '  `created_at` datetime NOT NULL,\n'
        '  `updated_at` datetime NOT NULL,\n'
        '  `finalized_at` datetime DEFAULT NULL,\n'
        '  `issuer_name` varchar(255) NOT NULL,\n'
        '  `issuer_address` varchar(500) NOT NULL,\n'
        '  `issuer_tax_number` varchar(50) DEFAULT NULL,\n'
        '  `issuer_vat_id` varchar(50) DEFAULT NULL,\n'
        '  `recipient_name` varchar(255) NOT NULL,\n'
        '  `recipient_address` varchar(500) NOT NULL,\n'
        '  `pdf_storage_path` varchar(500) DEFAULT NULL,\n'
        '  `pdf_sha256` varchar(64) DEFAULT NULL,\n'
        '  `pdf_size_bytes` int(11) DEFAULT NULL,\n'
        '  `pdf_created_at` datetime DEFAULT NULL,\n'
        '  `due_date` date DEFAULT NULL,\n'
        "  `document_type` varchar(20) NOT NULL DEFAULT 'invoice',\n"
        '  `cancellation_reason` varchar(500) DEFAULT NULL,\n'
        '  `cancelled_at` datetime DEFAULT NULL,\n'
        '  `original_invoice_id` int(11) DEFAULT NULL,\n'
        '  `issuer_bank_name` varchar(255) DEFAULT NULL,\n'
        '  `issuer_iban` varchar(34) DEFAULT NULL,\n'
        '  `issuer_bic` varchar(11) DEFAULT NULL,\n'
        '  `pdf_exported_at` datetime DEFAULT NULL,\n'
        '  `pdf_exported_by_user_id` int(11) DEFAULT NULL,\n'
        '  `pdf_export_remote_path` varchar(1200) DEFAULT NULL,\n'
        '  `issuer_phone` varchar(50) DEFAULT NULL,\n'
        '  `locale` varchar(10) DEFAULT NULL,\n'
        '  `language` varchar(5) DEFAULT NULL,\n'
        '  PRIMARY KEY (`id`),\n'
        '  UNIQUE KEY `invoice_number` (`invoice_number`),\n'
        '  UNIQUE KEY `original_invoice_id` (`original_invoice_id`),\n'
        '  KEY `ix_invoices_user_id` (`user_id`),\n'
        '  CONSTRAINT `invoices_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`),\n'
        '  CONSTRAINT `invoices_ibfk_2` FOREIGN KEY (`original_invoice_id`) REFERENCES `invoices` (`id`)\n'
        ') ENGINE=InnoDB'
    ),
    (
        'CREATE TABLE `monthly_base_fee_charges` (\n'
        '  `id` int(11) NOT NULL AUTO_INCREMENT,\n'
        '  `rfid_card_id` int(11) NOT NULL,\n'
        '  `rfid_assignment_id` int(11) NOT NULL,\n'
        '  `user_id` int(11) NOT NULL,\n'
        '  `fee_month` date NOT NULL,\n'
        '  `net_amount` decimal(12,4) NOT NULL,\n'
        '  `vat_rate` decimal(5,2) NOT NULL,\n'
        '  `invoiced` tinyint(1) NOT NULL DEFAULT 0,\n'
        '  `invoice_id` int(11) DEFAULT NULL,\n'
        '  `created_at` datetime NOT NULL,\n'
        '  `updated_at` datetime NOT NULL,\n'
        '  PRIMARY KEY (`id`),\n'
        '  UNIQUE KEY `uq_monthly_base_fee_charges_assignment_month` (`rfid_assignment_id`,`fee_month`),\n'
        '  KEY `fk_monthly_base_fee_charges_invoice` (`invoice_id`),\n'
        '  KEY `ix_monthly_base_fee_charges_user_month` (`user_id`,`fee_month`),\n'
        '  KEY `ix_monthly_base_fee_charges_rfid_card_id` (`rfid_card_id`),\n'
        '  CONSTRAINT `fk_monthly_base_fee_charges_invoice` FOREIGN KEY (`invoice_id`) REFERENCES `invoices` (`id`),\n'
        '  CONSTRAINT `fk_monthly_base_fee_charges_rfid_assignment` FOREIGN KEY (`rfid_assignment_id`) REFERENCES `rfid_card_assignments` (`id`),\n'
        '  CONSTRAINT `fk_monthly_base_fee_charges_rfid_card` FOREIGN KEY (`rfid_card_id`) REFERENCES `rfid_cards` (`id`),\n'
        '  CONSTRAINT `fk_monthly_base_fee_charges_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)\n'
        ') ENGINE=InnoDB'
    ),
    (
        'CREATE TABLE `password_reset_tokens` (\n'
        '  `id` int(11) NOT NULL AUTO_INCREMENT,\n'
        '  `user_id` int(11) NOT NULL,\n'
        '  `token_hash` varchar(64) NOT NULL,\n'
        '  `expires_at` datetime NOT NULL,\n'
        '  `used_at` datetime DEFAULT NULL,\n'
        '  `created_at` datetime NOT NULL,\n'
        '  PRIMARY KEY (`id`),\n'
        '  UNIQUE KEY `ix_password_reset_tokens_token_hash` (`token_hash`),\n'
        '  KEY `ix_password_reset_tokens_user_id` (`user_id`),\n'
        '  CONSTRAINT `password_reset_tokens_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE\n'
        ') ENGINE=InnoDB'
    ),
    (
        'CREATE TABLE `rfid_card_assignments` (\n'
        '  `id` int(11) NOT NULL AUTO_INCREMENT,\n'
        '  `rfid_card_id` int(11) NOT NULL,\n'
        '  `user_id` int(11) NOT NULL,\n'
        '  `valid_from` datetime NOT NULL,\n'
        '  `valid_to` datetime DEFAULT NULL,\n'
        '  `created_at` datetime NOT NULL,\n'
        '  `updated_at` datetime NOT NULL,\n'
        '  `note` varchar(255) DEFAULT NULL,\n'
        '  PRIMARY KEY (`id`),\n'
        '  UNIQUE KEY `uq_rfid_card_assignments_card_valid_from` (`rfid_card_id`,`valid_from`),\n'
        '  KEY `ix_rfid_card_assignments_user_id` (`user_id`),\n'
        '  KEY `ix_rfid_card_assignments_card_period` (`rfid_card_id`,`valid_from`,`valid_to`),\n'
        '  CONSTRAINT `fk_rfid_card_assignments_rfid_card_id_rfid_cards` FOREIGN KEY (`rfid_card_id`) REFERENCES `rfid_cards` (`id`),\n'
        '  CONSTRAINT `fk_rfid_card_assignments_user_id_users` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)\n'
        ') ENGINE=InnoDB'
    ),
    (
        'CREATE TABLE `rfid_cards` (\n'
        '  `id` int(11) NOT NULL AUTO_INCREMENT,\n'
        '  `rfid_number` varchar(100) NOT NULL,\n'
        '  `description` varchar(255) DEFAULT NULL,\n'
        '  `active` tinyint(1) NOT NULL,\n'
        '  `created_at` datetime NOT NULL,\n'
        '  `updated_at` datetime NOT NULL,\n'
        '  PRIMARY KEY (`id`),\n'
        '  UNIQUE KEY `rfid_number` (`rfid_number`)\n'
        ') ENGINE=InnoDB'
    ),
    (
        'CREATE TABLE `users` (\n'
        '  `id` int(11) NOT NULL AUTO_INCREMENT,\n'
        '  `email` varchar(255) NOT NULL,\n'
        '  `password_hash` varchar(255) NOT NULL,\n'
        '  `first_name` varchar(100) NOT NULL,\n'
        '  `last_name` varchar(100) NOT NULL,\n'
        '  `address` varchar(500) DEFAULT NULL,\n'
        '  `phone` varchar(50) DEFAULT NULL,\n'
        '  `invoice_delivery_email` tinyint(1) NOT NULL,\n'
        '  `invoice_delivery_post` tinyint(1) NOT NULL,\n'
        '  `active` tinyint(1) NOT NULL,\n'
        '  `created_at` datetime NOT NULL,\n'
        '  `updated_at` datetime NOT NULL,\n'
        '  `is_admin` tinyint(1) NOT NULL DEFAULT 0,\n'
        '  `last_login` datetime DEFAULT NULL,\n'
        '  `language` varchar(5) DEFAULT NULL,\n'
        '  PRIMARY KEY (`id`),\n'
        '  UNIQUE KEY `email` (`email`)\n'
        ') ENGINE=InnoDB'
    ),
]

# Grunddaten, die die bisherigen Migrationen angelegt haben
DATA = [
    (
        "INSERT INTO `global_settings` (`id`, `monthly_base_fee_net`, `monthly_base_fee_vat_rate`, `created_at`, `updated_at`, `app_name`, `invoice_payment_term_days`, `invoice_issuer_name`, `invoice_issuer_address`, `invoice_tax_number`, `invoice_vat_id`, `invoice_bank_name`, `invoice_iban`, `invoice_bic`, `invoice_number_prefix`, `smtp_use_database_settings`, `mail_sending_enabled`, `smtp_host`, `smtp_port`, `smtp_timeout_seconds`, `smtp_starttls`, `smtp_username`, `smtp_password_encrypted`, `mail_from_address`, `mail_from_name`, `password_min_length`, `password_require_uppercase`, `password_require_lowercase`, `password_require_digit`, `password_require_special`, `maintenance_mode`, `dashboard_note`, `invoice_pdf_format`, `frontend_base_url`, `password_reset_token_expire_minutes`, `postal_delivery_fee_net`, `mail_smime_enabled`, `mail_smime_pkcs12_data`, `mail_smime_pkcs12_filename`, `mail_smime_pkcs12_password_encrypted`, `billing_start_date`, `invoice_export_sftp_enabled`, `invoice_export_sftp_host`, `invoice_export_sftp_port`, `invoice_export_sftp_username`, `invoice_export_sftp_directory`, `invoice_girocode_enabled`, `invoice_issuer_phone`, `hager_username`, `hager_password_encrypted`, `hager_installation_id`, `hager_auto_import_enabled`, `hager_auto_import_interval_hours`, `hager_auto_import_start_time`, `hager_auto_import_last_started_at`, `hager_auto_import_last_finished_at`, `hager_auto_import_last_status`, `hager_auto_import_last_message`, `hager_last_successful_fetch_at`, `hager_serial_number`, `import_skip_empty_sessions`, `data_timezone`, `locale`, `currency`, `default_language`) VALUES (1,0.0000,19.00,'2026-09-30 23:44:22','2026-09-30 23:44:22','Witty-Accounting',0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,'RE',0,1,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,8,1,1,1,1,0,NULL,'standard','http://localhost:5173',60,0.0000,0,NULL,NULL,NULL,NULL,0,NULL,22,NULL,NULL,0,NULL,NULL,NULL,NULL,0,24,'03:00',NULL,NULL,NULL,NULL,NULL,NULL,0,NULL,'de-DE','EUR','de')"
    ),
]


def upgrade() -> None:
    # exec_driver_sql: SQL unverändert an MariaDB übergeben (kein Auswerten
    # von Doppelpunkten als Parameter);
    # no_parameters: auch "%" wird nicht als Platzhalter gedeutet
    connection = op.get_bind().execution_options(no_parameters=True)
    connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS=0")

    for statement in SCHEMA + DATA:
        connection.exec_driver_sql(statement)

    connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS=1")


def downgrade() -> None:
    raise NotImplementedError(
        "The baseline migration cannot be downgraded."
    )
