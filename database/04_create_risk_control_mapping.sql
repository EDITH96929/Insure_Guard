
-- InsureGuard
-- Risk-to-Control Mapping

CREATE TABLE IF NOT EXISTS insureguard.risk_control_mapping (

    risk_id VARCHAR(20) NOT NULL,

    control_id VARCHAR(20) NOT NULL,

    mapping_rationale TEXT NOT NULL,

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT risk_control_mapping_pk
        PRIMARY KEY (risk_id, control_id),

    CONSTRAINT risk_control_mapping_risk_fk
        FOREIGN KEY (risk_id)
        REFERENCES insureguard.risk_register(risk_id),

    CONSTRAINT risk_control_mapping_control_fk
        FOREIGN KEY (control_id)
        REFERENCES insureguard.control_library(control_id)

);
