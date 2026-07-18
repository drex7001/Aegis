"""Shared Phase 1 schema expectations."""

T4_TABLES = {
    "source",
    "source_record",
    "entity",
    "claim",
    "claim_relation",
    "review_queue",
    "case_file",
    "case_member",
    "authz_outbox",
}
EXPECTED_CHECKS = {
    "ck_source_record_status",
    "ck_case_file_status",
    "ck_claim_object_exactly_one",
    "ck_claim_no_self_reference",
    "ck_claim_event_time_order",
    "ck_claim_valid_date_order",
    "ck_claim_relation_relation",
    "ck_review_queue_status",
    "ck_authz_outbox_op",
}

ONTOLOGY_COLUMNS = {
    "source_type",
    "reliability_normalized",
    "entity_type",
    "predicate",
    "credibility_normalized",
    "verification_status",
    "analytic_confidence",
    "handling_code",
    "role",
}
