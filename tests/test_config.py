from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from moveflow.config.loader import CommunityCatalog, CommunityNotFoundError
from moveflow.config.schema import CommunityConfig, RuleConfig
from moveflow.domain.enums import OccupancyType, RequestType
from moveflow.policies.registry import UnknownRuleError, build_rules

COMMUNITIES = Path(__file__).resolve().parent.parent / "communities"


def test_all_community_files_load_and_build_their_rules():
    catalog = CommunityCatalog.from_directory(COMMUNITIES)
    assert {config.id for config in catalog.all()} == {"green-meadows", "skyline-towers"}
    for config in catalog.all():
        assert build_rules(config.rules)


def test_unknown_community_raises():
    with pytest.raises(CommunityNotFoundError):
        CommunityCatalog([]).get("nowhere")


def test_config_must_declare_core_fields():
    raw = yaml.safe_load((COMMUNITIES / "skyline_towers.yaml").read_text(encoding="utf-8"))
    raw["intake_fields"] = [field for field in raw["intake_fields"] if field["key"] != "move_date"]
    with pytest.raises(ValidationError, match="move_date"):
        CommunityConfig.model_validate(raw)


def test_unknown_rule_name_is_rejected():
    with pytest.raises(UnknownRuleError):
        build_rules([RuleConfig(name="no_pianos")])


def test_documents_depend_on_type_and_occupancy(green):
    tenant_move_in = {doc.doc_type for doc in green.documents_for(RequestType.MOVE_IN, OccupancyType.TENANT)}
    owner_move_in = {doc.doc_type for doc in green.documents_for(RequestType.MOVE_IN, OccupancyType.OWNER)}
    assert tenant_move_in == {"id_proof", "rental_agreement", "police_verification"}
    assert owner_move_in == {"id_proof", "sale_deed"}
    assert green.documents_for(RequestType.MOVE_IN, None) == []


def test_fields_are_filtered_by_request_type(skyline):
    move_in_keys = {spec.key for spec in skyline.fields_for(RequestType.MOVE_IN)}
    assert "parking_needed" in move_in_keys
    assert "deposit_refund_upi" not in move_in_keys
