
CREATE SCHEMA IF NOT EXISTS insureguard;

SET search_path TO insureguard, public;

-- 1. DEPARTMENTS
CREATE TABLE departments (
    department_id SERIAL PRIMARY KEY,
    department_name VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 2. ROLES
CREATE TABLE roles (
    role_id SERIAL PRIMARY KEY,
    role_name VARCHAR(100) NOT NULL UNIQUE,
    approval_limit NUMERIC(14,2) NOT NULL DEFAULT 0
        CHECK (approval_limit >= 0)
);

-- 3. EMPLOYEES
CREATE TABLE employees (
    employee_id VARCHAR(20) PRIMARY KEY,
    employee_name VARCHAR(150) NOT NULL,
    department_id INTEGER NOT NULL
        REFERENCES departments(department_id),
    role_id INTEGER NOT NULL
        REFERENCES roles(role_id),
    employee_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
        CHECK (employee_status IN ('ACTIVE', 'INACTIVE')),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 4. CUSTOMERS
CREATE TABLE customers (
    customer_id VARCHAR(20) PRIMARY KEY,
    customer_name VARCHAR(150) NOT NULL,
    region VARCHAR(80),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 5. POLICIES
CREATE TABLE policies (
    policy_id VARCHAR(30) PRIMARY KEY,
    customer_id VARCHAR(20) NOT NULL
        REFERENCES customers(customer_id),
    policy_type VARCHAR(30) NOT NULL
        CHECK (policy_type IN ('MOTOR', 'PROPERTY')),
    coverage_limit NUMERIC(14,2) NOT NULL
        CHECK (coverage_limit >= 0),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    policy_status VARCHAR(20) NOT NULL
        CHECK (policy_status IN ('ACTIVE', 'EXPIRED', 'CANCELLED')),
    CHECK (end_date >= start_date)
);

-- 6. CLAIMS
CREATE TABLE claims (
    claim_id VARCHAR(30) PRIMARY KEY,
    policy_id VARCHAR(30) NOT NULL
        REFERENCES policies(policy_id),
    claim_date DATE NOT NULL,
    claim_type VARCHAR(50),
    requested_amount NUMERIC(14,2) NOT NULL
        CHECK (requested_amount > 0),
    claim_status VARCHAR(25) NOT NULL
        CHECK (claim_status IN (
            'SUBMITTED', 'UNDER_REVIEW', 'APPROVED',
            'REJECTED', 'SETTLED', 'CLOSED'
        )),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 7. CLAIM APPROVALS
CREATE TABLE claim_approvals (
    approval_id VARCHAR(30) PRIMARY KEY,
    claim_id VARCHAR(30) NOT NULL
        REFERENCES claims(claim_id),
    approver_id VARCHAR(20) NOT NULL
        REFERENCES employees(employee_id),
    approval_status VARCHAR(20) NOT NULL
        CHECK (approval_status IN (
            'APPROVED', 'REJECTED', 'PENDING', 'REVOKED'
        )),
    approved_amount NUMERIC(14,2)
        CHECK (approved_amount IS NULL OR approved_amount >= 0),
    approval_timestamp TIMESTAMPTZ NOT NULL,
    approval_reference VARCHAR(50),
    UNIQUE (approval_id, claim_id)
);

-- 8. PAYMENTS
CREATE TABLE payments (
    payment_id VARCHAR(30) PRIMARY KEY,
    claim_id VARCHAR(30) NOT NULL
        REFERENCES claims(claim_id),
    approval_id VARCHAR(30),
    payment_reference VARCHAR(60),
    payment_amount NUMERIC(14,2) NOT NULL
        CHECK (payment_amount > 0),
    payment_date TIMESTAMPTZ NOT NULL,
    payment_status VARCHAR(20) NOT NULL
        CHECK (payment_status IN (
            'SUCCESSFUL', 'PENDING', 'FAILED',
            'REVERSED'
        )),
    executed_by VARCHAR(20)
        REFERENCES employees(employee_id),

    FOREIGN KEY (approval_id, claim_id)
        REFERENCES claim_approvals(approval_id, claim_id)
);

-- 9. CONTROL LIBRARY
CREATE TABLE control_library (
    control_id VARCHAR(20) PRIMARY KEY,
    control_name VARCHAR(150) NOT NULL,
    control_description TEXT NOT NULL,
    control_category VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL
        CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    control_frequency VARCHAR(30),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 10. CONTROL TEST RUNS
CREATE TABLE control_test_runs (
    run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_name VARCHAR(150) NOT NULL,
    executed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    executed_by VARCHAR(100),
    source_batch_id VARCHAR(50),
    run_status VARCHAR(20) NOT NULL DEFAULT 'RUNNING'
        CHECK (run_status IN (
            'RUNNING', 'COMPLETED', 'FAILED'
        ))
);

-- 11. CONTROL TEST RESULTS
CREATE TABLE control_tests (
    test_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id BIGINT NOT NULL
        REFERENCES control_test_runs(run_id),
    control_id VARCHAR(20) NOT NULL
        REFERENCES control_library(control_id),
    claim_id VARCHAR(30)
        REFERENCES claims(claim_id),
    payment_id VARCHAR(30)
        REFERENCES payments(payment_id),
    test_result VARCHAR(20) NOT NULL
        CHECK (test_result IN (
            'PASS', 'FAIL', 'NOT_APPLICABLE', 'ERROR'
        )),
    evidence JSONB,
    tested_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    CHECK (claim_id IS NOT NULL OR payment_id IS NOT NULL)
);

-- 12. EXCEPTIONS
CREATE TABLE exceptions (
    exception_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    test_id BIGINT NOT NULL
        REFERENCES control_tests(test_id),
    exception_type VARCHAR(100) NOT NULL,
    severity VARCHAR(20) NOT NULL
        CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    investigation_status VARCHAR(25) NOT NULL DEFAULT 'OPEN'
        CHECK (investigation_status IN (
            'OPEN', 'UNDER_REVIEW', 'CONFIRMED',
            'FALSE_POSITIVE', 'RESOLVED', 'CLOSED'
        )),
    analyst_notes TEXT,
    detected_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 13. RISK REGISTER
CREATE TABLE risk_register (
    risk_id VARCHAR(20) PRIMARY KEY,
    risk_name VARCHAR(150) NOT NULL,
    risk_description TEXT,
    likelihood INTEGER NOT NULL
        CHECK (likelihood BETWEEN 1 AND 5),
    impact INTEGER NOT NULL
        CHECK (impact BETWEEN 1 AND 5),
    inherent_score INTEGER GENERATED ALWAYS AS
        (likelihood * impact) STORED,
    control_effectiveness NUMERIC(4,3)
        CHECK (
            control_effectiveness IS NULL
            OR control_effectiveness BETWEEN 0 AND 1
        ),
    residual_score NUMERIC(7,3),
    risk_owner VARCHAR(20)
        REFERENCES employees(employee_id),
    risk_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
        CHECK (risk_status IN ('ACTIVE', 'MITIGATED', 'CLOSED')),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 14. REMEDIATION ACTIONS
CREATE TABLE remediation_actions (
    action_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    exception_id BIGINT NOT NULL
        REFERENCES exceptions(exception_id),
    owner_id VARCHAR(20) NOT NULL
        REFERENCES employees(employee_id),
    action_description TEXT NOT NULL,
    due_date DATE NOT NULL,
    action_status VARCHAR(20) NOT NULL DEFAULT 'OPEN'
        CHECK (action_status IN (
            'OPEN', 'IN_PROGRESS', 'PENDING_VERIFICATION',
            'COMPLETED', 'OVERDUE'
        )),
    completion_date DATE,
    verification_notes TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        completion_date IS NULL
        OR completion_date >= due_date
        OR action_status <> 'COMPLETED'
    )
);

-- 15. AUDIT LOGS
CREATE TABLE audit_logs (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL,
    entity_id VARCHAR(50) NOT NULL,
    action VARCHAR(50) NOT NULL,
    changed_by VARCHAR(100) NOT NULL,
    old_values JSONB,
    new_values JSONB,
    changed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- INDEXES
-- =====================================================

CREATE INDEX idx_policies_customer
    ON policies(customer_id);

CREATE INDEX idx_claims_policy
    ON claims(policy_id);

CREATE INDEX idx_claims_date
    ON claims(claim_date);

CREATE INDEX idx_approvals_claim
    ON claim_approvals(claim_id);

CREATE INDEX idx_payments_claim
    ON payments(claim_id);

CREATE INDEX idx_payments_reference
    ON payments(payment_reference);

CREATE INDEX idx_tests_control
    ON control_tests(control_id);

CREATE INDEX idx_tests_run
    ON control_tests(run_id);

CREATE INDEX idx_exceptions_status
    ON exceptions(investigation_status);

CREATE INDEX idx_remediation_owner_status
    ON remediation_actions(owner_id, action_status);

CREATE INDEX idx_audit_entity
    ON audit_logs(entity_type, entity_id);