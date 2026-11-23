-- Explicit, auditable verification for existing municipal accounts.
-- Run only after 007_municipal_iam.sql and before enabling the application.
-- Populate the temporary input table from approved municipal identity records;
-- do not commit employee IDs or evidence references to the repository.

BEGIN;

CREATE TEMPORARY TABLE approved_legacy_accounts (
    employee_id VARCHAR(50) PRIMARY KEY,
    role VARCHAR(20) NOT NULL CHECK (role IN ('driver', 'admin', 'collector')),
    approved_by_employee_id VARCHAR(50) NOT NULL,
    evidence_reference TEXT NOT NULL CHECK (length(trim(evidence_reference)) > 0),
    approved_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
) ON COMMIT DROP;

-- Example only; replace with individually verified, approved rows at execution:
-- INSERT INTO approved_legacy_accounts
--     (employee_id, role, approved_by_employee_id, evidence_reference)
-- VALUES ('<employee-id>', '<role>', '<approver-employee-id>', '<case-or-record-reference>');

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM approved_legacy_accounts approval
        LEFT JOIN users account
          ON account.employee_id = approval.employee_id
         AND account.role = approval.role
        WHERE account.id IS NULL
    ) THEN
        RAISE EXCEPTION 'Legacy IAM verification contains an unknown employee ID or mismatched role';
    END IF;

    -- An approval is only valid when it names an existing, active, verified
    -- Super Admin. Arbitrary or unverified employee IDs must never authorize
    -- legacy accounts (including other administrators).
    IF EXISTS (
        SELECT 1
        FROM approved_legacy_accounts approval
        WHERE NOT EXISTS (
            SELECT 1
            FROM users approver
            WHERE approver.employee_id = approval.approved_by_employee_id
              AND approver.role = 'admin'
              AND approver.is_super_admin IS TRUE
              AND approver.is_verified IS TRUE
              AND approver.is_active IS TRUE
              AND approver.account_status = 'active'
        )
    ) THEN
        RAISE EXCEPTION 'Every approver must be an existing active, verified Super Admin account';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM users account
        WHERE account.role IN ('driver', 'admin', 'collector')
          AND account.is_active IS TRUE
          AND account.account_status = 'active'
          AND account.is_verified IS FALSE
          AND NOT EXISTS (
              SELECT 1
              FROM approved_legacy_accounts approval
              WHERE approval.employee_id = account.employee_id
                AND approval.role = account.role
          )
    ) THEN
        RAISE EXCEPTION 'Approval input must cover every active legacy municipal account before enabling the application';
    END IF;
END;
$$;

WITH verified_accounts AS (
    UPDATE users account
    SET is_verified = TRUE,
        verified_at = approval.approved_at,
        approved_by_id = approver.id
    FROM approved_legacy_accounts approval
    JOIN users approver
      ON approver.employee_id = approval.approved_by_employee_id
    WHERE account.employee_id = approval.employee_id
      AND account.role = approval.role
      AND account.is_active IS TRUE
      AND account.account_status = 'active'
      AND account.is_verified IS FALSE
    RETURNING account.id, account.employee_id, approval.approved_by_employee_id,
              approval.evidence_reference, approval.approved_at
)
INSERT INTO security_audit_events (
    actor_id, target_user_id, actor_employee_id, target_employee_id,
    action, details, created_at
)
SELECT approver.id, verified.id, verified.approved_by_employee_id,
       verified.employee_id, 'legacy_account_verified',
       'Municipal identity evidence: ' || verified.evidence_reference,
       verified.approved_at
FROM verified_accounts verified
JOIN users approver
  ON approver.employee_id = verified.approved_by_employee_id;

COMMIT;
