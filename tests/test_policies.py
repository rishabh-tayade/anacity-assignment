from moveflow.domain.enums import RequestStatus, RequestType, Severity

from tests.conftest import make_request


def check(container, request):
    return {result.rule: result for result in container.compliance.check(request)}


def test_clean_owner_move_in_passes_everything(container):
    request = make_request(docs=("id_proof", "sale_deed"))
    assert all(result.passed for result in check(container, request).values())


def test_notice_period_is_enforced(container):
    result = check(container, make_request(move_date="2026-10-13"))["booking_window"]
    assert not result.passed and result.is_blocking
    assert "3 days notice" in result.message


def test_past_dates_are_rejected(container):
    assert not check(container, make_request(move_date="2026-10-01"))["booking_window"].passed


def test_blocked_weekday_and_festival(container):
    assert "Sundays" in check(container, make_request(move_date="2026-10-18"))["blocked_days"].message
    assert "Dussehra" in check(container, make_request(move_date="2026-10-20"))["blocked_days"].message


def test_same_rule_differs_by_community(container):
    sunday_in_skyline = make_request("skyline-towers", unit="T1-0901", move_date="2026-10-18", time_slot="first_half")
    assert check(container, sunday_in_skyline)["blocked_days"].passed


def test_slot_capacity_counts_active_requests_only(container):
    # The evening slot in Green Meadows takes one move.
    container.repository.save(make_request(unit="B-803", time_slot="evening", status=RequestStatus.UNDER_REVIEW))
    container.repository.save(make_request(unit="A-101", time_slot="evening", status=RequestStatus.CANCELLED))
    result = check(container, make_request(time_slot="evening"))["slot_capacity"]
    assert not result.passed and "fully booked" in result.message


def test_unknown_unit_is_a_blocker(container):
    result = check(container, make_request(unit="Z-999"))["unit_exists"]
    assert result.is_blocking


def test_move_in_to_occupied_unit_is_flagged_until_a_move_out_exists(container):
    move_in = make_request(unit="D-404", occupancy="tenant")
    result = check(container, move_in)["occupancy_consistency"]
    assert result.is_warning and "Meera Iyer" in result.message

    move_out = make_request(unit="D-404", request_type=RequestType.MOVE_OUT, status=RequestStatus.UNDER_REVIEW,
                            resident_name="Meera Iyer", move_date="2026-10-15")
    container.repository.save(move_out)
    assert check(container, move_in)["occupancy_consistency"].passed


def test_move_out_by_someone_else_is_flagged(container):
    request = make_request(unit="C-1102", request_type=RequestType.MOVE_OUT, resident_name="Random Person")
    assert not check(container, request)["occupancy_consistency"].passed


def test_dues_only_apply_to_move_out(container):
    move_out = make_request(unit="C-305", request_type=RequestType.MOVE_OUT, resident_name="Priya Nair",
                            occupancy="tenant", docs=("owner_noc",))
    results = check(container, move_out)
    assert results["dues_clearance"].severity is Severity.WARNING
    assert "4,500" in results["dues_clearance"].message
    assert "dues_clearance" not in check(container, make_request(unit="C-305"))


def test_duplicate_open_request_for_same_unit(container):
    container.repository.save(make_request(status=RequestStatus.UNDER_REVIEW))
    assert not check(container, make_request())["no_duplicate_request"].passed


def test_missing_documents_are_listed(container):
    result = check(container, make_request(occupancy="tenant", docs=("id_proof",)))["required_documents"]
    assert not result.passed
    assert "Rental agreement" in result.message and "Police verification" in result.message


def test_rules_skip_silently_when_information_is_missing(container):
    request = make_request()
    request.answers.pop("move_date")
    results = check(container, request)
    assert "booking_window" not in results and "slot_capacity" not in results


def test_slot_finder_suggests_valid_alternatives(container):
    request = make_request(move_date="2026-10-18")  # a Sunday
    options = container.slot_finder.alternatives(request)
    assert options
    for option in options:
        assert option.move_date.weekday() != 6
