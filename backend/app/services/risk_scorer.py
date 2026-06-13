"""Risk scoring service for compliance risk assessment.

This module provides deterministic rule-based risk scoring that evaluates
extracted entities and consistency check results to produce a risk score (0-100)
and risk level classification.

The service implements five risk categories:
1. Geolocation Risk (0-25 points) - Missing/unverified location, high-risk countries
2. Supplier Risk (0-25 points) - Missing info, no certification, conflicting data
3. Temporal Risk (0-15 points) - Date misalignments, recent changes
4. Compliance Risk (0-25 points) - Missing required documentation
5. Evidence Quality Risk (0-10 points) - Low extraction confidence, conflicts

Total score range: 0-100 (capped)
Risk levels: low (0-20), medium (21-40), high (41-70), critical (71-100)
"""

import logging
from datetime import UTC, date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.consistency import ConsistencyReport
from app.schemas.extraction import (
    ExtractionResult,
    LocationInfo,
    ProductInfo,
    ShipmentInfo,
    SupplierInfo,
)
from app.schemas.validation import ValidationResult

logger = logging.getLogger(__name__)

# Risk scoring constants (Coordinator-approved)
HIGH_RISK_COUNTRIES = {
    "IR",  # Iran
    "KP",  # North Korea
    "MM",  # Myanmar (restricted)
    "LY",  # Libya
    "SY",  # Syria
    "VE",  # Venezuela
}

# Temporal thresholds (days)
RECENT_SHIPMENT_DAYS = 7  # Shipment within last 7 days triggers recent activity check
SUPPLIER_UPDATE_DAYS = 30  # Supplier info updated within last 30 days

# Evidence quality thresholds (confidence scores 0.0-1.0)
LOW_CONFIDENCE_THRESHOLD = 0.7  # Below 0.7 = low quality (+10 points)
HIGH_CONFIDENCE_THRESHOLD = 0.8  # Above 0.8 = high quality (0 points)

# Risk point allocations by category
MAX_GEOLOCATION_POINTS = 25
MAX_SUPPLIER_POINTS = 25
MAX_TEMPORAL_POINTS = 15
MAX_COMPLIANCE_POINTS = 25
MAX_EVIDENCE_POINTS = 10
MAX_TOTAL_SCORE = 100


class RuleViolation(BaseModel):
    """Represents a single risk rule violation.

    Attributes:
        rule_name: Name of the violated rule (e.g., "no_location_data")
        category: Category it belongs to (geolocation, supplier, temporal, compliance, evidence)
        points: Points allocated for this violation (0-25)
        reason: Human-readable explanation of why this rule was triggered
        severity: Violation severity (low, medium, high, critical)
        remediation: Suggested corrective action (optional)
        evidence: Data that triggered this rule (optional)
    """

    model_config = ConfigDict(extra="forbid")

    rule_name: str = Field(..., min_length=1, max_length=100, description="Name of the rule")
    category: str = Field(
        ...,
        pattern="^(geolocation|supplier|temporal|compliance|evidence)$",
        description="Risk category",
    )
    points: int = Field(..., ge=0, le=25, description="Points for this violation")
    reason: str = Field(..., min_length=1, max_length=500, description="Why this rule triggered")
    severity: str = Field(
        ..., pattern="^(low|medium|high|critical)$", description="Violation severity"
    )
    remediation: str | None = Field(None, max_length=500, description="Suggested fix")
    evidence: dict[str, object] | None = Field(None, description="Data supporting this violation")


class RiskScoreResult(BaseModel):
    """Result of risk scoring analysis.

    Attributes:
        risk_score: Final risk score (0-100, capped at 100)
        risk_level: Risk level classification (low, medium, high, critical)
        violations: List of all detected rule violations
        violation_count: Total number of violations
        categories_affected: Which risk categories had violations
        calculated_at: When scoring was performed
    """

    model_config = ConfigDict(extra="forbid")

    risk_score: int = Field(..., ge=0, le=100, description="Risk score 0-100")
    risk_level: str = Field(
        ..., pattern="^(low|medium|high|critical)$", description="Risk level classification"
    )
    violations: list[RuleViolation] = Field(default_factory=list, description="All violations found")
    violation_count: int = Field(..., ge=0, description="Number of violations")
    categories_affected: list[str] = Field(default_factory=list, description="Affected categories")
    calculated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Calculation time")

    def to_assessment_dict(self) -> dict:
        """Convert to RiskAssessmentCreate-compatible format.

        Scales risk_score from 0-100 (int) to 0.0-1.0 (float) for database persistence.
        Confidence score is computed separately by Task 43 and will be added by Task 42.

        Returns:
            Dict with risk_level, risk_score (0.0-1.0), and rule_violations
        """
        return {
            "risk_level": self.risk_level,
            "risk_score": self.risk_score / 100.0,  # 0-100 → 0.0-1.0
            "rule_violations": [v.model_dump() for v in self.violations],
        }


class RiskScorer:
    """Deterministic rule-based risk scoring service.

    Provides risk assessment for compliance cases by applying deterministic rules
    to extracted entities and consistency check results. No external API calls or
    side effects - pure computation service.

    Attributes:
        logger: Logger for debug/info messages
    """

    def __init__(self) -> None:
        """Initialize RiskScorer."""
        self.logger = logger

    def score(
        self,
        entities: ExtractionResult,
        consistency_result: ConsistencyReport | None = None,
        validation_result: ValidationResult | None = None,
    ) -> RiskScoreResult:
        """Compute risk score based on rule violations.

        Evaluates extracted entities against five risk categories and returns
        a risk score (0-100) with detailed violation breakdown.

        Args:
            entities: Extracted supplier, product, location, shipment data
            consistency_result: Cross-document conflicts (optional, defaults to no conflicts)
            validation_result: Extraction quality metrics (optional)

        Returns:
            RiskScoreResult with score, level, and detailed violations

        Raises:
            ValueError: If entities is None or invalid

        Example:
            >>> scorer = RiskScorer()
            >>> result = scorer.score(
            ...     entities=extraction_result,
            ...     consistency_result=consistency_result,
            ...     validation_result=validation_result
            ... )
            >>> print(f"Risk Score: {result.risk_score}, Level: {result.risk_level}")
        """
        if not entities:
            raise ValueError("ExtractionResult is required")

        self.logger.debug(f"Starting risk scoring for document {entities.document_id}")

        all_violations: list[RuleViolation] = []

        # Evaluate each risk category
        all_violations.extend(self._evaluate_geolocation_risk(entities.location))
        all_violations.extend(
            self._evaluate_supplier_risk(entities.supplier, consistency_result)
        )
        all_violations.extend(
            self._evaluate_temporal_risk(
                entities.shipment, entities.supplier, consistency_result
            )
        )
        all_violations.extend(
            self._evaluate_compliance_risk(entities.product, entities.shipment)
        )
        all_violations.extend(
            self._evaluate_evidence_quality_risk(
                entities.extraction_confidence, validation_result
            )
        )

        # Calculate total score and risk level
        total_score = self._calculate_total_score(all_violations)
        risk_level = self._get_risk_level(total_score)

        # Extract affected categories
        categories_affected = sorted(set(v.category for v in all_violations))

        result = RiskScoreResult(
            risk_score=total_score,
            risk_level=risk_level,
            violations=all_violations,
            violation_count=len(all_violations),
            categories_affected=categories_affected,
        )

        self.logger.info(
            f"Risk scoring complete: score={result.risk_score}, level={result.risk_level}, "
            f"violations={len(all_violations)}"
        )

        return result

    def _evaluate_geolocation_risk(self, location: LocationInfo | None) -> list[RuleViolation]:
        """Evaluate geolocation risk (0-25 points, capped per category).

        Checks for missing location data, high-risk countries, and unverified locations.

        Args:
            location: LocationInfo from ExtractionResult

        Returns:
            List of RuleViolation objects for geolocation violations (total ≤ 25 points)
        """
        violations: list[RuleViolation] = []

        if not location:
            violations.append(
                RuleViolation(
                    rule_name="no_location_data",
                    category="geolocation",
                    points=MAX_GEOLOCATION_POINTS,
                    reason="No location information found in document",
                    severity="critical",
                    remediation="Obtain confirmed country of origin or destination",
                    evidence={"location": None},
                )
            )
            return violations

        # Check for high-risk country
        country = location.country.upper() if location.country else None
        if country in HIGH_RISK_COUNTRIES:
            violations.append(
                RuleViolation(
                    rule_name="high_risk_country",
                    category="geolocation",
                    points=20,
                    reason=f"Country '{location.country}' is on high-risk list (OFAC sanctions)",
                    severity="critical",
                    remediation="Escalate to compliance team for review",
                    evidence={"country": location.country, "risk_profile": location.risk_profile},
                )
            )

        # Check for unverified location
        if not location.geolocation_verified:
            violations.append(
                RuleViolation(
                    rule_name="unverified_location",
                    category="geolocation",
                    points=10,
                    reason="Location has not been verified with coordinates",
                    severity="medium",
                    remediation="Verify location coordinates and update geolocation_verified flag",
                    evidence={
                        "geolocation_verified": False,
                        "country": location.country,
                    },
                )
            )

        # Enforce per-category cap (max 25 points)
        total_geo = sum(v.points for v in violations)
        if total_geo > MAX_GEOLOCATION_POINTS:
            excess = total_geo - MAX_GEOLOCATION_POINTS
            violations[-1] = violations[-1].model_copy(
                update={"points": violations[-1].points - excess}
            )

        return violations

    def _evaluate_supplier_risk(
        self, supplier: SupplierInfo | None, consistency_result: ConsistencyReport | None = None
    ) -> list[RuleViolation]:
        """Evaluate supplier risk (0-25 points).

        Checks for missing supplier info, lack of certification, and conflicts.

        Args:
            supplier: SupplierInfo from ExtractionResult
            consistency_result: ConsistencyReport with conflict data (optional)

        Returns:
            List of RuleViolation objects for supplier violations
        """
        violations: list[RuleViolation] = []

        if not supplier:
            violations.append(
                RuleViolation(
                    rule_name="no_supplier_info",
                    category="supplier",
                    points=MAX_SUPPLIER_POINTS,
                    reason="No supplier information found in document",
                    severity="critical",
                    remediation="Obtain supplier declaration or business registration",
                    evidence={"supplier": None},
                )
            )
            return violations

        # Check for missing or invalid certification
        cert_status = supplier.certification_status
        if not cert_status or cert_status.lower() in ("none", "unknown"):
            violations.append(
                RuleViolation(
                    rule_name="no_certification",
                    category="supplier",
                    points=15,
                    reason="Supplier lacks valid certification status",
                    severity="high",
                    remediation="Request supplier certification or compliance documentation",
                    evidence={"certification_status": cert_status},
                )
            )

        # Check for supplier conflicts across documents (from Task 40)
        if consistency_result:
            for conflict in consistency_result.field_conflicts:
                if conflict.field.startswith("supplier"):
                    violations.append(
                        RuleViolation(
                            rule_name="supplier_conflict",
                            category="supplier",
                            points=10,
                            reason=f"Conflicting supplier information found in field '{conflict.field}'",
                            severity="high",
                            remediation="Reconcile supplier data across all documents",
                            evidence={
                                "field": conflict.field,
                                "conflicting_values": conflict.values,
                            },
                        )
                    )

        return violations

    def _evaluate_temporal_risk(
        self,
        shipment: ShipmentInfo | None,
        supplier: SupplierInfo | None,
        consistency_result: ConsistencyReport | None = None,
    ) -> list[RuleViolation]:
        """Evaluate temporal risk (0-15 points, capped per category).

        Checks for date misalignments, future dates, and recent changes.

        Args:
            shipment: ShipmentInfo from ExtractionResult
            supplier: SupplierInfo from ExtractionResult
            consistency_result: ConsistencyReport with temporal conflicts (optional)

        Returns:
            List of RuleViolation objects for temporal violations (total ≤ 15 points)
        """
        violations: list[RuleViolation] = []

        # Check for temporal conflicts detected by Task 40
        # Only emit one temporal conflict violation per category (max 15 points)
        if consistency_result and consistency_result.temporal_conflicts:
            violations.append(
                RuleViolation(
                    rule_name="temporal_conflict",
                    category="temporal",
                    points=MAX_TEMPORAL_POINTS,
                    reason="Date misalignments detected across documents",
                    severity="critical",
                    remediation="Review and correct date information in source documents",
                    evidence={
                        "conflict_count": len(consistency_result.temporal_conflicts),
                        "conflict_types": [c.conflict_type for c in consistency_result.temporal_conflicts],
                    },
                )
            )

        # Check for recent shipment dates (volatility indicator)
        if shipment and shipment.shipment_date:
            days_ago = (date.today() - shipment.shipment_date).days
            if 0 <= days_ago <= RECENT_SHIPMENT_DAYS:
                violations.append(
                    RuleViolation(
                        rule_name="recent_shipment",
                        category="temporal",
                        points=5,
                        reason=f"Shipment occurred recently ({days_ago} days ago), indicating active supply chain",
                        severity="low",
                        remediation="Monitor shipment for completion and verify documentation",
                        evidence={"shipment_date": shipment.shipment_date.isoformat()},
                    )
                )

        # Check for recent supplier updates
        if supplier and supplier.last_updated:
            days_ago = (datetime.now(UTC) - supplier.last_updated).days
            if 0 <= days_ago <= SUPPLIER_UPDATE_DAYS:
                violations.append(
                    RuleViolation(
                        rule_name="recent_supplier_update",
                        category="temporal",
                        points=5,
                        reason=f"Supplier information recently changed ({days_ago} days ago)",
                        severity="medium",
                        remediation="Verify reasons for recent supplier data changes",
                        evidence={"last_updated": supplier.last_updated.isoformat()},
                    )
                )

        return violations

    def _evaluate_compliance_risk(self, product: ProductInfo | None, shipment: ShipmentInfo | None) -> list[RuleViolation]:
        """Evaluate compliance risk (0-25 points).

        Checks for missing required documentation and incomplete declarations.

        Args:
            product: ProductInfo from ExtractionResult
            shipment: ShipmentInfo from ExtractionResult

        Returns:
            List of RuleViolation objects for compliance violations
        """
        violations: list[RuleViolation] = []

        # Track which required fields are missing
        missing_docs = []

        # Check for tracking number (shipping documentation)
        if not shipment or not shipment.tracking_number:
            missing_docs.append("tracking_number")

        # Check for HS code (customs declaration)
        if not product or not product.hs_code:
            missing_docs.append("hs_code")

        # Check for product origin (customs declaration)
        if not product or not product.origin_country:
            missing_docs.append("origin_country")

        # If any required doc missing, add violation
        if missing_docs:
            violations.append(
                RuleViolation(
                    rule_name="missing_required_documentation",
                    category="compliance",
                    points=MAX_COMPLIANCE_POINTS,
                    reason=f"Missing required documentation: {', '.join(missing_docs)}",
                    severity="critical",
                    remediation="Obtain missing documentation from supplier or carrier",
                    evidence={"missing_fields": missing_docs},
                )
            )

        return violations

    def _evaluate_evidence_quality_risk(
        self, extraction_confidence: float, validation_result: ValidationResult | None = None
    ) -> list[RuleViolation]:
        """Evaluate evidence quality risk (0-10 points, capped per category).

        Checks extraction confidence and validation conflicts.

        Args:
            extraction_confidence: Confidence score from ExtractionResult (0.0-1.0)
            validation_result: ValidationResult with quality metrics (optional)

        Returns:
            List of RuleViolation objects for evidence quality violations (total ≤ 10 points)
        """
        violations: list[RuleViolation] = []

        # Check extraction confidence
        if extraction_confidence < LOW_CONFIDENCE_THRESHOLD:
            violations.append(
                RuleViolation(
                    rule_name="low_extraction_confidence",
                    category="evidence",
                    points=MAX_EVIDENCE_POINTS,
                    reason=f"Extraction confidence {extraction_confidence:.1%} is below {LOW_CONFIDENCE_THRESHOLD:.0%}",
                    severity="high",
                    remediation="Re-extract with improved prompts or manual review",
                    evidence={"extraction_confidence": extraction_confidence},
                )
            )
        elif extraction_confidence < HIGH_CONFIDENCE_THRESHOLD:
            violations.append(
                RuleViolation(
                    rule_name="medium_extraction_confidence",
                    category="evidence",
                    points=5,
                    reason=f"Extraction confidence {extraction_confidence:.1%} is below {HIGH_CONFIDENCE_THRESHOLD:.0%}",
                    severity="medium",
                    remediation="Review extracted values for accuracy",
                    evidence={"extraction_confidence": extraction_confidence},
                )
            )

        # Check validation conflicts
        if validation_result and validation_result.failures:
            violations.append(
                RuleViolation(
                    rule_name="validation_failures",
                    category="evidence",
                    points=5,
                    reason=f"Validation found {len(validation_result.failures)} issues during extraction",
                    severity="medium",
                    remediation="Address validation failures: check field values and formats",
                    evidence={"failure_count": len(validation_result.failures)},
                )
            )

        # Enforce per-category cap (max 10 points)
        total_evidence = sum(v.points for v in violations)
        if total_evidence > MAX_EVIDENCE_POINTS:
            excess = total_evidence - MAX_EVIDENCE_POINTS
            violations[-1] = violations[-1].model_copy(
                update={"points": violations[-1].points - excess}
            )

        return violations

    def _calculate_total_score(self, violations: list[RuleViolation]) -> int:
        """Calculate total risk score from violations.

        Sums points from all violations and caps at MAX_TOTAL_SCORE.

        Args:
            violations: List of RuleViolation objects

        Returns:
            Total score (0-100)
        """
        total = sum(v.points for v in violations)
        capped_score = min(total, MAX_TOTAL_SCORE)
        return capped_score

    def _get_risk_level(self, score: int) -> str:
        """Map risk score to risk level classification.

        Args:
            score: Risk score (0-100)

        Returns:
            Risk level string: "low", "medium", "high", or "critical"
        """
        if score <= 20:
            return "low"
        elif score <= 40:
            return "medium"
        elif score <= 70:
            return "high"
        else:
            return "critical"
