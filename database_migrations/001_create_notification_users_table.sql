-- Migration: Create notification_users table for admin/superadmin notification recipients
-- Description: This table stores which admin/superadmin users should receive cooling period summary emails
-- Author: System
-- Created: 2024-12-17

CREATE TABLE IF NOT EXISTS notification_users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by INT NOT NULL,
    CONSTRAINT fk_notification_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_notification_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT,
    UNIQUE KEY uk_notification_user_id (user_id)
);

-- Add index for faster lookups
CREATE INDEX idx_notification_users_user_id ON notification_users(user_id);
CREATE INDEX idx_notification_users_created_at ON notification_users(created_at);

-- This table will be used by the send_admin_cooling_period_summary Celery task
-- to send consolidated cooling period reports to all registered notification users (admins/superadmins)
