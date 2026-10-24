"""Trusted security-policy consumption at the existing asset boundaries.

This module is the Runtime side of the engineering-ci trusted security-policy
contract ([ECI #56], merged as ``c40fb69``): it consumes a **verified policy
snapshot** produced by ``engineering-ci policy receive`` and evaluates it
against a real ``AssetSelection``, producing the same
``engineering-ci-security-policy-decision`` document ECI #57 consumes. It
never re-implements publication, reception, trust anchoring or state storage —
those stay with the publisher — and it never treats a selection's own
``AssetPolicy.enabled`` as a trusted security decision.

Identity follows the #27 record model: policy rules match the tool primary key
(``tool_id``) plus actual version, platform, source and artifact digest, and
optionally ``access_id`` when a rule really limits one entry. Decisions bind
the current policy identity and the original selection identity separately and
rewrite neither.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from .assets import AssetSelection
from .documents import ToolRuntimeError, canonical

SNAPSHOT_KIND = "engineering-ci-security-policy-snapshot"
DECISION_KIND = "engineering-ci-security-policy-decision"
SCHEMA_VERSION = 1

EFFECTS = ("allow", "deny")
DECISIONS = ("allow", "deny", "unknown")
REASONS = (
    "matched_allow",
    "matched_deny",
    "no_matching_rule",
    "policy_expired",
    "policy_not_yet_valid",
    "protected_profile_not_covered",
    "policy_superseded",
)
# Refusal codes reused from the publisher contract; none is invented here.
REFUSAL_CODES = (
    "policy_snapshot_invalid",
    "policy_state_missing",
    "policy_rollback",
    "asset_invalid",
    "clock_invalid",
)

_ASSET_FIELDS = frozenset(
    {"tool_id", "access_id", "version", "platform", "source", "digest"}
)
_SNAPSHOT_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "policy",
        "publication",
        "release",
        "verified_at",
        "state",
    }
)
_POLICY_KEYS = frozenset(
    {
        "revision",
        "minimum_revision",
        "issued_at",
        "not_before",
        "expires_at",
        "publisher",
        "protected_profiles",
        "rules",
        "sha256",
        "size",
    }
)
_HEX64 = re.compile(r"[0-9a-f]{64}")
_TEXT = re.compile(r"\S.*", re.DOTALL)


class SecurityPolicyError(ToolRuntimeError):
    """A stable policy refusal code from the publisher contract."""

    def __init__(self, code):
        self.code = code
        super().__init__(f"Security policy: {code}")


def _text(value, code, limit):
    if not isinstance(value, str) or not value or len(value) > limit:
        raise SecurityPolicyError(code)
    return value


def _timestamp(value, code):
    if not isinstance(value, str) or not value:
        raise SecurityPolicyError(code)
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        raise SecurityPolicyError(code) from None
    if moment.tzinfo is None:
        raise SecurityPolicyError(code)
    return moment


def _instant(now):
    if now is None:
        return datetime.now(UTC)
    if isinstance(now, str):
        return _timestamp(now, "clock_invalid")
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise SecurityPolicyError("clock_invalid")
    return now


def _moment_text(moment):
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _selector(value, code):
    # Publisher rule selectors are complete records (ECI ``_asset``): every
    # field is present; null is the explicit wildcard, not an omitted key.
    if not isinstance(value, Mapping) or set(value) != _ASSET_FIELDS:
        raise SecurityPolicyError(code)
    value = dict(value)
    _text(value.get("tool_id"), code, 128)
    for name, limit in (
        ("access_id", 128),
        ("version", 128),
        ("source", 2048),
        ("digest", 128),
    ):
        if value.get(name) is not None:
            _text(value[name], code, limit)
    platform = value.get("platform")
    if platform is not None:
        if not isinstance(platform, Mapping) or set(platform) != {"os", "arch"}:
            raise SecurityPolicyError(code)
        _text(platform["os"], code, 32)
        _text(platform["arch"], code, 32)
        value["platform"] = dict(platform)
    return value


@dataclass(frozen=True)
class SecurityPolicySnapshot:
    """One verified publisher snapshot, parsed and structurally validated.

    Verification (source, digest, release identity, anti-rollback against the
    receiver state) happened at reception and is NOT redone here; decision-time
    window re-checks and rule evaluation are performed per decision.
    """

    document: Mapping

    def __post_init__(self):
        code = "policy_snapshot_invalid"
        value = self.document
        if not isinstance(value, Mapping) or set(value) != _SNAPSHOT_KEYS:
            raise SecurityPolicyError(code)
        if (
            type(value["schema_version"]) is not int
            or value["schema_version"] != SCHEMA_VERSION
            or value["kind"] != SNAPSHOT_KIND
        ):
            raise SecurityPolicyError(code)
        policy = value["policy"]
        if not isinstance(policy, Mapping) or set(policy) != _POLICY_KEYS:
            raise SecurityPolicyError(code)
        for name in ("revision", "minimum_revision"):
            if type(policy[name]) is not int or not 1 <= policy[name] <= 2_147_483_647:
                raise SecurityPolicyError(code)
        if policy["minimum_revision"] > policy["revision"]:
            raise SecurityPolicyError(code)
        issued = _timestamp(policy["issued_at"], code)
        before = _timestamp(policy["not_before"], code)
        after = _timestamp(policy["expires_at"], code)
        if before >= after or issued > after:
            raise SecurityPolicyError(code)
        publisher = policy["publisher"]
        if (
            not isinstance(publisher, Mapping)
            or set(publisher) != {"repository", "workflow"}
            or not isinstance(publisher["repository"], str)
            or not isinstance(publisher["workflow"], str)
        ):
            raise SecurityPolicyError(code)
        profiles = policy["protected_profiles"]
        if (
            not isinstance(profiles, list)
            or not 1 <= len(profiles) <= 32
            or any(
                not isinstance(item, str) or not 1 <= len(item) <= 128
                for item in profiles
            )
            or len(set(profiles)) != len(profiles)
        ):
            raise SecurityPolicyError(code)
        if not isinstance(policy["sha256"], str) or not _HEX64.fullmatch(
            policy["sha256"]
        ):
            raise SecurityPolicyError(code)
        if type(policy["size"]) is not int or policy["size"] < 1:
            raise SecurityPolicyError(code)
        rules = policy["rules"]
        if not isinstance(rules, list) or not 1 <= len(rules) <= 1000:
            raise SecurityPolicyError(code)
        identifiers = set()
        for rule in rules:
            if not isinstance(rule, Mapping) or set(rule) != {
                "rule_id",
                "effect",
                "reason",
                "asset",
            }:
                raise SecurityPolicyError(code)
            _text(rule["rule_id"], code, 128)
            if rule["rule_id"] in identifiers:
                raise SecurityPolicyError(code)
            identifiers.add(rule["rule_id"])
            if rule["effect"] not in EFFECTS:
                raise SecurityPolicyError(code)
            _text(rule["reason"], code, 512)
            # Publisher selectors are complete records; absent fields are
            # explicit wildcards (null), not omitted keys.
            _selector(rule["asset"], code)
        publication = value["publication"]
        if (
            not isinstance(publication, Mapping)
            or not isinstance(publication.get("sha256"), str)
            or not isinstance(publication.get("published_at"), str)
        ):
            raise SecurityPolicyError(code)
        if not isinstance(value["release"], Mapping):
            raise SecurityPolicyError(code)
        _timestamp(value["verified_at"], code)
        if not isinstance(value["state"], Mapping):
            raise SecurityPolicyError(code)
        canonical(value)

    @property
    def revision(self):
        return self.document["policy"]["revision"]

    @property
    def policy_sha256(self):
        return self.document["policy"]["sha256"]

    @property
    def protected_profiles(self):
        return tuple(self.document["policy"]["protected_profiles"])

    def not_before(self):
        return _timestamp(
            self.document["policy"]["not_before"], "policy_snapshot_invalid"
        )

    def expires_at(self):
        return _timestamp(
            self.document["policy"]["expires_at"], "policy_snapshot_invalid"
        )


def _asset_from_selection(selection, access_id):
    """Echo the exact asset facts of this selection; nothing is invented."""
    if not isinstance(selection, AssetSelection):
        raise SecurityPolicyError("asset_invalid")
    if access_id is not None:
        _text(access_id, "asset_invalid", 256)
    return {
        "tool_id": selection.tool_id,
        "access_id": access_id,
        "version": selection.release.version,
        "platform": {"os": selection.target.os, "arch": selection.target.arch},
        "source": selection.release.source,
        "digest": selection.release.sha256,
    }


def _matches(selector, asset):
    for field in ("tool_id", "access_id", "version", "source", "digest"):
        if selector[field] is not None and selector[field] != asset[field]:
            return False
    return not (
        selector["platform"] is not None and selector["platform"] != asset["platform"]
    )


def decide_asset_admission(
    snapshot,
    selection,
    *,
    protected_profile,
    access_id=None,
    now=None,
    superseded=False,
    minimum_revision=None,
):
    """Evaluate one real selection against the currently accepted snapshot.

    Mirrors the publisher's decision contract exactly — deny wins over allow,
    an unmatched asset is ``unknown``/``no_matching_rule`` and never allowed,
    the window is re-checked at decision time, an uncovered protected profile
    is ``unknown``, and a superseded snapshot is ``unknown``. The decision
    document keeps the current policy identity and the original selection
    identity (its own ``AssetPolicy`` revision) separate; neither is rewritten.
    """
    if not isinstance(snapshot, SecurityPolicySnapshot):
        raise SecurityPolicyError("policy_snapshot_invalid")
    moment = _instant(now)
    if minimum_revision is not None and (
        type(minimum_revision) is not int or minimum_revision < 1
    ):
        raise SecurityPolicyError("policy_snapshot_invalid")
    if minimum_revision is not None and snapshot.revision < minimum_revision:
        # Advance-only floor from the receiver's protected state; an older
        # snapshot cannot re-admit a revoked asset.
        raise SecurityPolicyError("policy_rollback")
    if protected_profile is not None:
        _text(protected_profile, "policy_snapshot_invalid", 256)
    policy = snapshot.document["policy"]
    if superseded:
        decision, reason, rule_id = "unknown", "policy_superseded", None
    elif moment > snapshot.expires_at():
        decision, reason, rule_id = "unknown", "policy_expired", None
    elif moment < snapshot.not_before():
        decision, reason, rule_id = "unknown", "policy_not_yet_valid", None
    elif (
        protected_profile is not None
        and protected_profile not in snapshot.protected_profiles
    ):
        decision, reason, rule_id = "unknown", "protected_profile_not_covered", None
    else:
        asset = _asset_from_selection(selection, access_id)
        decision, reason, rule_id = "unknown", "no_matching_rule", None
        for rule in policy["rules"]:
            if rule["effect"] == "deny" and _matches(rule["asset"], asset):
                decision, reason, rule_id = "deny", "matched_deny", rule["rule_id"]
                break
        else:
            for rule in policy["rules"]:
                if rule["effect"] == "allow" and _matches(rule["asset"], asset):
                    decision, reason, rule_id = (
                        "allow",
                        "matched_allow",
                        rule["rule_id"],
                    )
                    break
    asset = _asset_from_selection(selection, access_id)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": DECISION_KIND,
        "decision": decision,
        "allowed": decision == "allow",
        "reason": reason,
        "rule_id": rule_id,
        "policy": {
            "revision": snapshot.revision,
            "sha256": snapshot.policy_sha256,
            "release": dict(snapshot.document["release"]),
        },
        "selection": {
            "selection_id": selection.selection_id,
            "policy_revision": selection.policy.revision,
        },
        "asset": asset,
        "protected_profile": protected_profile,
        "evaluated_at": _moment_text(moment),
    }


def admit_protected_asset(
    snapshot,
    selection,
    *,
    protected_profile,
    spec=None,
    scope=None,
    access_id=None,
    now=None,
    superseded=False,
    minimum_revision=None,
):
    """The boundary gate: current policy allow **and** existing scope admission.

    A protected call requires an actual snapshot and an ``allow`` decision; a
    missing trusted basis is ``policy_state_missing`` (never unknown-as-
    allowed) and refusals raise ``SecurityPolicyError`` carrying the decision
    reason. The existing ``DiscoveryScope.admit`` still applies independently —
    a security allow never widens scope, and scope never substitutes for
    policy. Unprotected callers (``protected_profile=None``) are untouched and
    keep the existing explicit authorization behavior. Preparation success,
    cached bytes and old receipts never replace this admission.
    """
    if protected_profile is None:
        return None
    if snapshot is None:
        raise SecurityPolicyError("policy_state_missing")
    decision = decide_asset_admission(
        snapshot,
        selection,
        protected_profile=protected_profile,
        access_id=access_id,
        now=now,
        superseded=superseded,
        minimum_revision=minimum_revision,
    )
    if not decision["allowed"]:
        raise SecurityPolicyError(decision["reason"])
    if spec is not None and scope is not None:
        scope.admit(spec)
    return decision
