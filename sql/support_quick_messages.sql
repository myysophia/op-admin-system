-- support_quick_messages 表结构（客服快捷消息）
CREATE TABLE IF NOT EXISTS support_quick_messages (
    id VARCHAR(36) PRIMARY KEY,
    title VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
    image_key VARCHAR(255),
    image_url TEXT,
    sort_order INTEGER NOT NULL DEFAULT 100,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by VARCHAR(64) NOT NULL,
    created_by_name VARCHAR(128),
    updated_by VARCHAR(64),
    updated_by_name VARCHAR(128),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_support_quick_messages_active ON support_quick_messages(is_active);
CREATE INDEX IF NOT EXISTS idx_support_quick_messages_sort ON support_quick_messages(sort_order, created_at DESC);

COMMENT ON TABLE support_quick_messages IS 'Support module quick message templates with optional images';
