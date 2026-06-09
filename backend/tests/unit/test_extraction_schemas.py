"""Unit tests for extraction schemas (Task 38).

Tests Pydantic models for entity extraction:
- SupplierInfo, ProductInfo, LocationInfo, ShipmentInfo, ExtractionResult
- Field validation, normalization, edge cases
"""

from datetime import date, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.extraction import (
    ExtractionResult,
    LocationInfo,
    ProductInfo,
    ShipmentInfo,
    SupplierInfo,
)


class TestSupplierInfo:
    """Tests for SupplierInfo schema."""

    def test_valid_creation_minimal(self):
        """Test creating SupplierInfo with required fields only."""
        supplier = SupplierInfo(
            name="Acme Corp",
            country_of_origin="CN",
        )
        assert supplier.name == "Acme Corp"
        assert supplier.country_of_origin == "CN"
        assert supplier.registration_number is None
        assert supplier.business_type is None
        assert supplier.certification_status is None
        assert supplier.last_updated is None

    def test_valid_creation_full(self):
        """Test creating SupplierInfo with all fields."""
        now = datetime.now()
        supplier = SupplierInfo(
            name="Acme Corp",
            country_of_origin="CN",
            registration_number="12345678",
            business_type="manufacturer",
            certification_status="certified",
            last_updated=now,
        )
        assert supplier.name == "Acme Corp"
        assert supplier.country_of_origin == "CN"
        assert supplier.registration_number == "12345678"
        assert supplier.business_type == "manufacturer"
        assert supplier.certification_status == "certified"
        assert supplier.last_updated == now

    def test_missing_required_name(self):
        """Test that missing name raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            SupplierInfo(country_of_origin="CN")
        assert "name" in str(exc_info.value).lower()

    def test_missing_required_country(self):
        """Test that missing country_of_origin raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            SupplierInfo(name="Acme Corp")
        assert "country_of_origin" in str(exc_info.value).lower()

    def test_name_normalization_strip_whitespace(self):
        """Test that name is stripped of leading/trailing whitespace."""
        supplier = SupplierInfo(
            name="  Acme Corp  ",
            country_of_origin="CN",
        )
        assert supplier.name == "Acme Corp"

    def test_country_normalization_strip_whitespace(self):
        """Test that country_of_origin is stripped."""
        supplier = SupplierInfo(
            name="Acme Corp",
            country_of_origin="  CN  ",
        )
        assert supplier.country_of_origin == "CN"

    def test_empty_string_name_raises_error(self):
        """Test that empty or whitespace-only name raises error."""
        with pytest.raises(ValidationError) as exc_info:
            SupplierInfo(
                name="   ",
                country_of_origin="CN",
            )
        assert "empty" in str(exc_info.value).lower() or "whitespace" in str(exc_info.value).lower()

    def test_empty_string_country_raises_error(self):
        """Test that empty or whitespace-only country raises error."""
        with pytest.raises(ValidationError) as exc_info:
            SupplierInfo(
                name="Acme Corp",
                country_of_origin="   ",
            )
        assert "empty" in str(exc_info.value).lower() or "whitespace" in str(exc_info.value).lower()

    def test_unicode_in_name(self):
        """Test that unicode characters in name are preserved."""
        supplier = SupplierInfo(
            name="Société Générale",
            country_of_origin="FR",
        )
        assert supplier.name == "Société Générale"

    def test_max_length_name(self):
        """Test that very long names are accepted up to max_length."""
        long_name = "A" * 255
        supplier = SupplierInfo(
            name=long_name,
            country_of_origin="CN",
        )
        assert supplier.name == long_name

    def test_max_length_name_exceeded(self):
        """Test that names exceeding max_length are rejected."""
        long_name = "A" * 256
        with pytest.raises(ValidationError):
            SupplierInfo(
                name=long_name,
                country_of_origin="CN",
            )

    def test_registration_number_normalization(self):
        """Test that registration_number is normalized."""
        supplier = SupplierInfo(
            name="Acme Corp",
            country_of_origin="CN",
            registration_number="  123-456-789  ",
        )
        assert supplier.registration_number == "123-456-789"


class TestProductInfo:
    """Tests for ProductInfo schema."""

    def test_valid_creation_minimal(self):
        """Test creating ProductInfo with required fields only."""
        product = ProductInfo(name="Steel Coils")
        assert product.name == "Steel Coils"
        assert product.hs_code is None
        assert product.category is None

    def test_valid_creation_full(self):
        """Test creating ProductInfo with all fields."""
        product = ProductInfo(
            name="Steel Coils",
            hs_code="72081100",
            category="metals",
            origin_country="CN",
            quantity=500.0,
            unit="kg",
        )
        assert product.name == "Steel Coils"
        assert product.hs_code == "72081100"
        assert product.category == "metals"
        assert product.origin_country == "CN"
        assert product.quantity == 500.0
        assert product.unit == "kg"

    def test_missing_required_name(self):
        """Test that missing name raises ValidationError."""
        with pytest.raises(ValidationError):
            ProductInfo()

    def test_name_normalization(self):
        """Test that name is stripped."""
        product = ProductInfo(name="  Steel Coils  ")
        assert product.name == "Steel Coils"

    def test_empty_name_raises_error(self):
        """Test that empty name raises error."""
        with pytest.raises(ValidationError):
            ProductInfo(name="   ")

    def test_quantity_normalization_negative_rejected(self):
        """Test that negative quantity is rejected."""
        with pytest.raises(ValidationError):
            ProductInfo(name="Steel Coils", quantity=-1.0)

    def test_quantity_zero_accepted(self):
        """Test that zero quantity is accepted."""
        product = ProductInfo(name="Steel Coils", quantity=0.0)
        assert product.quantity == 0.0

    def test_quantity_nan_rejected(self):
        """Test that NaN quantity is rejected."""
        with pytest.raises(ValidationError):
            ProductInfo(name="Steel Coils", quantity=float("nan"))

    def test_quantity_infinity_rejected(self):
        """Test that infinity quantity is rejected."""
        with pytest.raises(ValidationError):
            ProductInfo(name="Steel Coils", quantity=float("inf"))

    def test_hs_code_normalization(self):
        """Test that HS code is normalized."""
        product = ProductInfo(
            name="Steel Coils",
            hs_code="  72081100  ",
        )
        assert product.hs_code == "72081100"

    def test_unicode_in_product_name(self):
        """Test that unicode in product name is preserved."""
        product = ProductInfo(name="Acier Laminé")
        assert product.name == "Acier Laminé"


class TestLocationInfo:
    """Tests for LocationInfo schema."""

    def test_valid_creation_minimal(self):
        """Test creating LocationInfo with required fields only."""
        location = LocationInfo(country="CN")
        assert location.country == "CN"
        assert location.region is None
        assert location.risk_profile is None
        assert location.geolocation_verified is False

    def test_valid_creation_full(self):
        """Test creating LocationInfo with all fields."""
        location = LocationInfo(
            country="CN",
            region="Guangdong",
            risk_profile="medium-risk",
            geolocation_verified=True,
        )
        assert location.country == "CN"
        assert location.region == "Guangdong"
        assert location.risk_profile == "medium-risk"
        assert location.geolocation_verified is True

    def test_missing_required_country(self):
        """Test that missing country raises ValidationError."""
        with pytest.raises(ValidationError):
            LocationInfo()

    def test_country_normalization(self):
        """Test that country is normalized."""
        location = LocationInfo(country="  CN  ")
        assert location.country == "CN"

    def test_region_normalization(self):
        """Test that region is normalized."""
        location = LocationInfo(
            country="CN",
            region="  Guangdong  ",
        )
        assert location.region == "Guangdong"

    def test_geolocation_verified_default(self):
        """Test that geolocation_verified defaults to False."""
        location = LocationInfo(country="CN")
        assert location.geolocation_verified is False

    def test_geolocation_verified_true(self):
        """Test that geolocation_verified can be set to True."""
        location = LocationInfo(country="CN", geolocation_verified=True)
        assert location.geolocation_verified is True


class TestShipmentInfo:
    """Tests for ShipmentInfo schema."""

    def test_valid_creation_minimal(self):
        """Test creating ShipmentInfo with no fields (all optional)."""
        shipment = ShipmentInfo()
        assert shipment.shipment_date is None
        assert shipment.arrival_date is None
        assert shipment.origin_port is None
        assert shipment.destination_port is None
        assert shipment.transport_mode is None
        assert shipment.tracking_number is None

    def test_valid_creation_full(self):
        """Test creating ShipmentInfo with all fields."""
        shipment_date = date(2026, 6, 1)
        arrival_date = date(2026, 6, 15)
        shipment = ShipmentInfo(
            shipment_date=shipment_date,
            arrival_date=arrival_date,
            origin_port="Shanghai Port",
            destination_port="Rotterdam Port",
            transport_mode="sea",
            tracking_number="BL123456789",
        )
        assert shipment.shipment_date == shipment_date
        assert shipment.arrival_date == arrival_date
        assert shipment.origin_port == "Shanghai Port"
        assert shipment.destination_port == "Rotterdam Port"
        assert shipment.transport_mode == "sea"
        assert shipment.tracking_number == "BL123456789"

    def test_dates_normalization(self):
        """Test that dates are properly parsed."""
        shipment = ShipmentInfo(
            shipment_date=date(2026, 6, 1),
            arrival_date=date(2026, 6, 15),
        )
        assert shipment.shipment_date == date(2026, 6, 1)
        assert shipment.arrival_date == date(2026, 6, 15)

    def test_port_normalization(self):
        """Test that port names are normalized."""
        shipment = ShipmentInfo(
            origin_port="  Shanghai Port  ",
            destination_port="  Rotterdam Port  ",
        )
        assert shipment.origin_port == "Shanghai Port"
        assert shipment.destination_port == "Rotterdam Port"

    def test_transport_mode_normalization(self):
        """Test that transport_mode is normalized."""
        shipment = ShipmentInfo(transport_mode="  sea  ")
        assert shipment.transport_mode == "sea"

    def test_tracking_number_normalization(self):
        """Test that tracking_number is normalized."""
        shipment = ShipmentInfo(tracking_number="  BL123456789  ")
        assert shipment.tracking_number == "BL123456789"


class TestExtractionResult:
    """Tests for ExtractionResult schema."""

    def test_valid_creation(self):
        """Test creating ExtractionResult with all required fields."""
        doc_id = uuid4()
        now = datetime.now()
        result = ExtractionResult(
            document_id=doc_id,
            supplier=SupplierInfo(name="Acme", country_of_origin="CN"),
            product=ProductInfo(name="Steel"),
            location=LocationInfo(country="CN"),
            shipment=ShipmentInfo(),
            extraction_confidence=0.95,
            extracted_at=now,
            model_used="openai/gpt-4o-mini",
        )
        assert result.document_id == doc_id
        assert result.supplier.name == "Acme"
        assert result.product.name == "Steel"
        assert result.location.country == "CN"
        assert result.extraction_confidence == 0.95
        assert result.extracted_at == now
        assert result.model_used == "openai/gpt-4o-mini"

    def test_missing_required_document_id(self):
        """Test that missing document_id raises error."""
        with pytest.raises(ValidationError):
            ExtractionResult(
                supplier=SupplierInfo(name="Acme", country_of_origin="CN"),
                product=ProductInfo(name="Steel"),
                location=LocationInfo(country="CN"),
                shipment=ShipmentInfo(),
                extraction_confidence=0.95,
                extracted_at=datetime.now(),
                model_used="openai/gpt-4o-mini",
            )

    def test_missing_required_confidence(self):
        """Test that missing extraction_confidence raises error."""
        with pytest.raises(ValidationError):
            ExtractionResult(
                document_id=uuid4(),
                supplier=SupplierInfo(name="Acme", country_of_origin="CN"),
                product=ProductInfo(name="Steel"),
                location=LocationInfo(country="CN"),
                shipment=ShipmentInfo(),
                extracted_at=datetime.now(),
                model_used="openai/gpt-4o-mini",
            )

    def test_confidence_out_of_range_low(self):
        """Test that confidence < 0.0 is rejected."""
        with pytest.raises(ValidationError):
            ExtractionResult(
                document_id=uuid4(),
                supplier=SupplierInfo(name="Acme", country_of_origin="CN"),
                product=ProductInfo(name="Steel"),
                location=LocationInfo(country="CN"),
                shipment=ShipmentInfo(),
                extraction_confidence=-0.1,
                extracted_at=datetime.now(),
                model_used="openai/gpt-4o-mini",
            )

    def test_confidence_out_of_range_high(self):
        """Test that confidence > 1.0 is rejected."""
        with pytest.raises(ValidationError):
            ExtractionResult(
                document_id=uuid4(),
                supplier=SupplierInfo(name="Acme", country_of_origin="CN"),
                product=ProductInfo(name="Steel"),
                location=LocationInfo(country="CN"),
                shipment=ShipmentInfo(),
                extraction_confidence=1.1,
                extracted_at=datetime.now(),
                model_used="openai/gpt-4o-mini",
            )

    def test_confidence_nan_rejected(self):
        """Test that NaN confidence is rejected."""
        with pytest.raises(ValidationError):
            ExtractionResult(
                document_id=uuid4(),
                supplier=SupplierInfo(name="Acme", country_of_origin="CN"),
                product=ProductInfo(name="Steel"),
                location=LocationInfo(country="CN"),
                shipment=ShipmentInfo(),
                extraction_confidence=float("nan"),
                extracted_at=datetime.now(),
                model_used="openai/gpt-4o-mini",
            )

    def test_confidence_infinity_rejected(self):
        """Test that infinity confidence is rejected."""
        with pytest.raises(ValidationError):
            ExtractionResult(
                document_id=uuid4(),
                supplier=SupplierInfo(name="Acme", country_of_origin="CN"),
                product=ProductInfo(name="Steel"),
                location=LocationInfo(country="CN"),
                shipment=ShipmentInfo(),
                extraction_confidence=float("inf"),
                extracted_at=datetime.now(),
                model_used="openai/gpt-4o-mini",
            )

    def test_confidence_edge_values(self):
        """Test that edge values 0.0 and 1.0 are accepted."""
        doc_id = uuid4()
        now = datetime.now()

        # Test 0.0
        result_low = ExtractionResult(
            document_id=doc_id,
            supplier=SupplierInfo(name="Acme", country_of_origin="CN"),
            product=ProductInfo(name="Steel"),
            location=LocationInfo(country="CN"),
            shipment=ShipmentInfo(),
            extraction_confidence=0.0,
            extracted_at=now,
            model_used="openai/gpt-4o-mini",
        )
        assert result_low.extraction_confidence == 0.0

        # Test 1.0
        result_high = ExtractionResult(
            document_id=uuid4(),
            supplier=SupplierInfo(name="Acme", country_of_origin="CN"),
            product=ProductInfo(name="Steel"),
            location=LocationInfo(country="CN"),
            shipment=ShipmentInfo(),
            extraction_confidence=1.0,
            extracted_at=now,
            model_used="openai/gpt-4o-mini",
        )
        assert result_high.extraction_confidence == 1.0

    def test_nested_supplier_validation(self):
        """Test that invalid supplier causes validation error."""
        with pytest.raises(ValidationError):
            ExtractionResult(
                document_id=uuid4(),
                supplier=SupplierInfo(name="   ", country_of_origin="CN"),
                product=ProductInfo(name="Steel"),
                location=LocationInfo(country="CN"),
                shipment=ShipmentInfo(),
                extraction_confidence=0.95,
                extracted_at=datetime.now(),
                model_used="openai/gpt-4o-mini",
            )

    def test_nested_product_validation(self):
        """Test that invalid product causes validation error."""
        with pytest.raises(ValidationError):
            ExtractionResult(
                document_id=uuid4(),
                supplier=SupplierInfo(name="Acme", country_of_origin="CN"),
                product=ProductInfo(name="   "),
                location=LocationInfo(country="CN"),
                shipment=ShipmentInfo(),
                extraction_confidence=0.95,
                extracted_at=datetime.now(),
                model_used="openai/gpt-4o-mini",
            )

    def test_model_used_normalization(self):
        """Test that model_used is stored as provided."""
        result = ExtractionResult(
            document_id=uuid4(),
            supplier=SupplierInfo(name="Acme", country_of_origin="CN"),
            product=ProductInfo(name="Steel"),
            location=LocationInfo(country="CN"),
            shipment=ShipmentInfo(),
            extraction_confidence=0.95,
            extracted_at=datetime.now(),
            model_used="openai/gpt-4o-mini",
        )
        assert result.model_used == "openai/gpt-4o-mini"
