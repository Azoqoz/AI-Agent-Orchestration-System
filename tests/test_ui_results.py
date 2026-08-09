from src.ui.components import final_decision_fields


def fields_for(state):
    return dict(final_decision_fields(state))


def test_case_225_final_decision_shows_priority_and_sla(orchestrator):
    state = orchestrator.start("Determine the priority and SLA status of CASE-225.")

    assert fields_for(state) == {
        "Outcome": "Completed",
        "Priority": "High",
        "SLA status": "Breached",
        "SLA breached": "Yes",
        "Overdue hours": "60 hours",
    }


def test_generic_case_review_displays_lookup_facts(orchestrator):
    state = orchestrator.start("What is CASE-220?")

    assert fields_for(state) == {
        "Outcome": "Completed",
        "Case ID": "CASE-220",
        "Customer ID": "CUST-101",
        "Case type": "Refund",
        "Case status": "Open",
        "Issue": "Duplicate purchase",
        "Created": "2026-01-14T06:00:00+00:00",
        "Order ID": "ORD-501",
        "Purchase amount": "$120.00",
        "Purchase date": "2026-01-08",
        "Purchase age": "7 days",
        "Usage": "5%",
    }


def test_case_220_final_decision_keeps_refund_results(orchestrator):
    waiting = orchestrator.start(
        "Review CASE-220, check eligibility, calculate the refund, and prepare a customer response."
    )
    state = orchestrator.resume(waiting["task_id"], "approved", "Evidence checked")

    fields = fields_for(state)
    assert fields["Eligibility"] == "Eligible"
    assert fields["Recommended refund"] == "$115.00"
    assert fields["Approval decision"] == "Approved"
    assert fields["Report generated"] == "Yes"
    assert fields["Customer response ready"] == "Yes"
    assert "Priority" not in fields and "SLA status" not in fields


def test_case_999_final_decision_stays_safe_and_omits_missing_results(orchestrator):
    state = orchestrator.start("Check priority of CASE-999")

    assert state["status"] == "failed"
    assert fields_for(state) == {"Outcome": "Failed"}


def test_customer_open_case_summary_is_visible_in_final_decision(orchestrator):
    state = orchestrator.start("Check customer CUST-104 and summarize all open cases.")
    fields = fields_for(state)

    assert fields["Customer ID"] == "CUST-104"
    assert fields["Account status"] == "Active"
    assert fields["Open cases"] == "3"
    assert fields["Open case summary"] == (
        "CASE-228 · refund/open · Moderate usage; "
        "CASE-225 · refund/open · High value repeated contact"
    )


def test_manual_review_policy_result_is_visible_in_final_decision(orchestrator):
    state = orchestrator.start("Review CASE-223 and determine whether it needs manual review.")
    fields = fields_for(state)

    assert fields["Eligibility"] == "Manual Review"
    assert fields["Human review required"] == "Yes"
    assert fields["Policy reason"] == "Purchase is 15-30 days old with usage at most 25%"


def test_recent_approved_refund_history_result_is_visible(orchestrator):
    waiting = orchestrator.start(
        "Review CASE-220, check eligibility, calculate the refund, and prepare a customer response."
    )
    approved = orchestrator.resume(waiting["task_id"], "approved", "History seed")
    state = orchestrator.start("Show the most recent approved refund case.")
    fields = fields_for(state)

    assert fields["Retrieved task ID"] == approved["task_id"]
    assert fields["Retrieved case ID"] == "CASE-220"
    assert fields["Retrieved customer ID"] == "CUST-101"
    assert fields["Retrieved refund"] == "$115.00"
    assert fields["Retrieved approval"] == "Approved"
    assert fields["Completed"]
