
SET search_path TO insureguard, public;

INSERT INTO control_library (
    control_id,
    control_name,
    control_description,
    control_category,
    severity,
    control_frequency,
    is_active
)
VALUES

(
    'CT-001',
    'Payment Authorization Verification',
    'Verify that each payment is supported by an approved claim authorization.',
    'AUTHORIZATION',
    'CRITICAL',
    'CONTINUOUS',
    TRUE
),

(
    'CT-002',
    'Duplicate Payment Detection',
    'Identify repeated payment transactions using claim, reference, amount and transaction status.',
    'PAYMENT',
    'HIGH',
    'CONTINUOUS',
    TRUE
),

(
    'CT-003',
    'Settlement Amount Verification',
    'Verify that cumulative successful payments do not exceed the approved settlement amount.',
    'PAYMENT',
    'CRITICAL',
    'CONTINUOUS',
    TRUE
),

(
    'CT-004',
    'Documentation Completeness',
    'Verify that mandatory claim documents are available and complete before approval.',
    'DOCUMENTATION',
    'HIGH',
    'PER_CLAIM',
    FALSE
),

(
    'CT-005',
    'Claim Payment Reconciliation',
    'Reconcile claim approvals and payment transactions to identify missing or inconsistent financial records.',
    'RECONCILIATION',
    'HIGH',
    'CONTINUOUS',
    TRUE
),

(
    'CT-006',
    'Segregation of Duties',
    'Verify that the employee approving a claim is different from the employee executing its payment.',
    'GOVERNANCE',
    'HIGH',
    'CONTINUOUS',
    TRUE
),

(
    'CT-007',
    'Approval Authority Verification',
    'Verify that the approving employee has sufficient delegated authority for the approved amount.',
    'AUTHORIZATION',
    'CRITICAL',
    'PER_APPROVAL',
    TRUE
),

(
    'CT-008',
    'Settlement SLA Monitoring',
    'Identify claims whose settlement exceeds the applicable business-defined settlement deadline.',
    'OPERATIONS',
    'MEDIUM',
    'DAILY',
    FALSE
)

ON CONFLICT (control_id)
DO UPDATE SET
    control_name = EXCLUDED.control_name,
    control_description = EXCLUDED.control_description,
    control_category = EXCLUDED.control_category,
    severity = EXCLUDED.severity,
    control_frequency = EXCLUDED.control_frequency,
    is_active = EXCLUDED.is_active;
