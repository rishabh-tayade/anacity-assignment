"""Demo residents and a few requests in different states, so the admin queue isn't empty.

Dates are relative to today so the demo stays valid whenever it is run.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from moveflow.domain.enums import Actor, RequestStatus, RequestType
from moveflow.domain.models import Message, MoveRequest, TimelineEvent, UploadedDocument
from moveflow.repositories.base import RequestRepository


@dataclass(frozen=True)
class DemoResident:
    name: str
    phone: str
    note: str


DEMO_RESIDENTS: dict[str, list[DemoResident]] = {
    "green-meadows": [
        DemoResident("Ananya Rao", "9876543210", "New tenant, about to move into B-1204"),
        DemoResident("Farhan Qureshi", "9822000004", "Owner of C-1102, the desk asked him for more info"),
        DemoResident("Priya Nair", "9822000002", "Tenant in C-305 moving out, has pending dues"),
    ],
    "skyline-towers": [
        DemoResident("Kavita Joshi", "9811111111", "Owner of T1-1203, planning to move out"),
        DemoResident("Ishaan Verma", "9811111112", "New tenant looking at T2-1101"),
    ],
}


def seed_demo_data(repository: RequestRepository, today: date) -> None:
    if repository.list():
        return
    for request in _demo_requests(today):
        repository.save(request)


def _demo_requests(today: date) -> list[MoveRequest]:
    def day(offset: int) -> str:
        # Green Meadows blocks Sundays; nudge demo dates off them.
        moved = today + timedelta(days=offset)
        return (moved + timedelta(days=1) if moved.weekday() == 6 else moved).isoformat()

    return [
        _request(
            "green-meadows", RequestType.MOVE_IN, RequestStatus.UNDER_REVIEW,
            {"resident_name": "Vikram Shah", "phone": "9822000001", "unit": "B-803", "occupancy": "owner",
             "move_date": day(4), "time_slot": "morning", "household_size": 4, "vehicle_numbers": "KA01AB1234",
             "movers_company": "Leo Packers"},
            docs=["id_proof", "sale_deed"],
        ),
        _request(
            "green-meadows", RequestType.MOVE_OUT, RequestStatus.UNDER_REVIEW,
            {"resident_name": "Priya Nair", "phone": "9822000002", "unit": "C-305", "occupancy": "tenant",
             "move_date": day(6), "time_slot": "afternoon", "movers_company": None,
             "forwarding_address": "14 Lake View Road, Kochi", "access_cards": 2},
            docs=["owner_noc"],
        ),
        _request(
            "green-meadows", RequestType.MOVE_IN, RequestStatus.UNDER_REVIEW,
            {"resident_name": "Karan Malhotra", "phone": "9822000003", "unit": "D-404", "occupancy": "tenant",
             "move_date": day(8), "time_slot": "evening", "household_size": 2, "vehicle_numbers": None,
             "movers_company": "City Movers"},
            docs=["id_proof", "rental_agreement", "police_verification"],
        ),
        _request(
            "green-meadows", RequestType.MOVE_OUT, RequestStatus.NEEDS_INFO,
            {"resident_name": "Farhan Qureshi", "phone": "9822000004", "unit": "C-1102", "occupancy": "owner",
             "move_date": day(10), "time_slot": "morning", "movers_company": "Agarwal Packers",
             "forwarding_address": "Flat 3, Palm Residency, Hyderabad", "access_cards": 3},
            admin_message="Hi Farhan, could you confirm whether the unit will be rented out after you leave? "
                          "If so, please ask the new tenant to raise a move-in request.",
        ),
        _request(
            "green-meadows", RequestType.MOVE_OUT, RequestStatus.APPROVED,
            {"resident_name": "Sanjay Gupta", "phone": "9822000005", "unit": "A-702", "occupancy": "tenant",
             "move_date": day(3), "time_slot": "morning", "movers_company": "Leo Packers",
             "forwarding_address": "22 MG Road, Pune", "access_cards": 2},
            docs=["owner_noc"],
            admin_message="Approved. Please return both access cards at the desk on move day.",
        ),
        _request(
            "skyline-towers", RequestType.MOVE_IN, RequestStatus.APPROVED,
            {"resident_name": "Rohit Kulkarni", "phone": "9811111113", "unit": "T1-0901", "occupancy": "owner",
             "move_date": day(2), "time_slot": "first_half", "parking_needed": True, "pets": False},
            docs=["id_proof"],
            approved_by_agent=True,
        ),
        _request(
            "skyline-towers", RequestType.MOVE_OUT, RequestStatus.UNDER_REVIEW,
            {"resident_name": "Arjun Desai", "phone": "9811111114", "unit": "T2-0502", "occupancy": "tenant",
             "move_date": day(5), "time_slot": "second_half", "deposit_refund_upi": "arjun@okbank"},
        ),
    ]


def _request(
    community_id: str,
    request_type: RequestType,
    status: RequestStatus,
    answers: dict,
    docs: list[str] | None = None,
    admin_message: str = "",
    approved_by_agent: bool = False,
) -> MoveRequest:
    request = MoveRequest(
        community_id=community_id,
        request_type=request_type,
        status=status,
        answers=answers,
        documents=[UploadedDocument(doc_type=doc, file_name=f"{doc}.pdf") for doc in docs or []],
    )
    request.timeline = [TimelineEvent(actor=Actor.RESIDENT, action="Submitted")]
    if approved_by_agent:
        request.timeline.append(TimelineEvent(actor=Actor.AGENT, action="Auto-approved",
                                              note="All community rules passed."))
    else:
        request.timeline.append(TimelineEvent(actor=Actor.SYSTEM, action="Sent for admin review"))
    if status is RequestStatus.NEEDS_INFO:
        request.timeline.append(TimelineEvent(actor=Actor.ADMIN, action="More information requested"))
    if status is RequestStatus.APPROVED and not approved_by_agent:
        request.timeline.append(TimelineEvent(actor=Actor.ADMIN, action="Approved"))
    if admin_message:
        request.messages.append(Message(sender=Actor.ADMIN, text=admin_message))
    return request
