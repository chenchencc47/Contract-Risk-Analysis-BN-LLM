CREATE DATABASE IF NOT EXISTS contract_risk CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE contract_risk;

CREATE TABLE IF NOT EXISTS contracts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    contract_name VARCHAR(255) NOT NULL,
    contract_type VARCHAR(100) NOT NULL DEFAULT '销售合同',
    contract_text LONGTEXT NOT NULL,
    file_name VARCHAR(255) NULL,
    party_a VARCHAR(255) NULL,
    party_b VARCHAR(255) NULL,
    contract_amount DECIMAL(18, 2) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_contract_name (contract_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS reports (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    contract_id BIGINT UNSIGNED NOT NULL,
    report_version INT NOT NULL,
    review_party VARCHAR(32) NOT NULL DEFAULT 'buyer',
    overall_risk_level VARCHAR(32) NULL,
    overall_p_high DECIMAL(8, 4) NULL,
    summary_text TEXT NULL,
    report_content_md LONGTEXT NOT NULL,
    bn_counterfactual_count INT NOT NULL DEFAULT 0,
    review_duration_ms INT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_report_version (contract_id, review_party, report_version),
    KEY idx_reports_contract_party_created (contract_id, review_party, created_at),
    CONSTRAINT fk_reports_contract FOREIGN KEY (contract_id) REFERENCES contracts (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS report_risks (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    report_id BIGINT UNSIGNED NOT NULL,
    risk_name VARCHAR(255) NOT NULL,
    risk_level VARCHAR(32) NOT NULL,
    clause_category VARCHAR(100) NULL,
    ai_confidence DECIMAL(8, 4) NULL,
    bn_verified TINYINT(1) NOT NULL DEFAULT 0,
    suggestion_text TEXT NULL,
    sort_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_report_risks_report_order (report_id, sort_order),
    CONSTRAINT fk_report_risks_report FOREIGN KEY (report_id) REFERENCES reports (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS report_counterfactuals (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    report_id BIGINT UNSIGNED NOT NULL,
    dimension_name VARCHAR(255) NOT NULL,
    dimension_level_p_high DECIMAL(8, 4) NULL,
    dimension_improved DECIMAL(8, 4) NULL,
    dimension_delta DECIMAL(8, 4) NULL,
    overall_p_high DECIMAL(8, 4) NULL,
    overall_improved DECIMAL(8, 4) NULL,
    overall_delta DECIMAL(8, 4) NULL,
    ai_rating VARCHAR(64) NULL,
    consensus VARCHAR(64) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_report_counterfactuals_report (report_id),
    CONSTRAINT fk_report_counterfactuals_report FOREIGN KEY (report_id) REFERENCES reports (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS company_redlines (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    contract_type VARCHAR(100) NOT NULL,
    category VARCHAR(64) NOT NULL,
    rule_id VARCHAR(128) NOT NULL,
    label VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    severity VARCHAR(64) NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_company_redline (contract_type, rule_id),
    KEY idx_company_redlines_lookup (contract_type, category, is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS bn_feedback (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    report_id BIGINT UNSIGNED NOT NULL,
    node_name VARCHAR(255) NOT NULL,
    verdict VARCHAR(32) NOT NULL,
    reviewer_note TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_bn_feedback_report (report_id),
    KEY idx_bn_feedback_node (node_name),
    CONSTRAINT fk_bn_feedback_report FOREIGN KEY (report_id) REFERENCES reports (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
