-- ============================================================
-- Seed: Notification Service Database
-- ============================================================

CREATE TABLE IF NOT EXISTS notifications_log (
    notification_id  SERIAL PRIMARY KEY,
    customer_id      INTEGER        NOT NULL,
    customer_email   VARCHAR(150)   NOT NULL,
    customer_phone   VARCHAR(15)    NOT NULL,
    event_type       VARCHAR(50)    NOT NULL,
    channel          VARCHAR(10)    NOT NULL CHECK (channel IN ('EMAIL','SMS')),
    status           VARCHAR(20)    NOT NULL DEFAULT 'PENDING'
                     CHECK (status IN ('PENDING','SENT','FAILED','SKIPPED')),
    payload          JSONB          NOT NULL DEFAULT '{}',
    retry_count      SMALLINT       NOT NULL DEFAULT 0,
    sent_at          TIMESTAMPTZ,
    created_at       TIMESTAMPTZ    NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_notif_customer ON notifications_log(customer_id);
CREATE INDEX IF NOT EXISTS idx_notif_status   ON notifications_log(status);
-- Notification logs are populated at runtime by the notification service consumer.
