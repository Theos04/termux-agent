"""Built-in domain skills auto-registration."""

from agent.skill_registry.registry import registry

# Commercial skills
from .commercial import (
    ResolveEntitySkill,
    DisambiguateProductSkill,
    DetectCommercialIntentSkill,
    CalculateTrueLandedCostSkill,
    DiscoverAlternativeSupplierSkill,
    PredictStockoutSkill,
    DetectQuoteAnomalySkill,
    ReconcileThreeWayMatchSkill,
)

# Customer skills
from .customer import (
    CalculateNextBestActionSkill,
    DetectRelationshipDecaySkill,
    RecoverAbandonedOrderSkill,
)

# Governance skills
from .governance import (
    EnforcePolicySkill,
    CheckConsentSkill,
    AuditTrailRecordSkill,
)

# Reliability skills
from .reliability import (
    EnforceIdempotencySkill,
    CompensateTransactionSkill,
    ReconcileStateSkill,
)


def register_all_builtin_skills():
    """Register all predefined skills into the central registry."""
    skills = [
        # Commercial & Procurement
        ResolveEntitySkill(),
        DisambiguateProductSkill(),
        DetectCommercialIntentSkill(),
        CalculateTrueLandedCostSkill(),
        DiscoverAlternativeSupplierSkill(),
        PredictStockoutSkill(),
        DetectQuoteAnomalySkill(),
        ReconcileThreeWayMatchSkill(),
        # Customer
        CalculateNextBestActionSkill(),
        DetectRelationshipDecaySkill(),
        RecoverAbandonedOrderSkill(),
        # Governance
        EnforcePolicySkill(),
        CheckConsentSkill(),
        AuditTrailRecordSkill(),
        # Reliability
        EnforceIdempotencySkill(),
        CompensateTransactionSkill(),
        ReconcileStateSkill(),
    ]
    for s in skills:
        registry.register(s)


# Auto-register on import
register_all_builtin_skills()
