"""
Email Validation Service.

Validates email addresses before sending to reduce bounces.
Multiple validation strategies from basic regex to DNS checks.
"""

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import dns.resolver
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..logging_config import get_logger

logger = get_logger("services.email_validation")


# =============================================================================
# Models
# =============================================================================


class ValidationCheck(BaseModel):
    """Result of a single validation check."""

    name: str
    passed: bool
    reason: str | None = None


class ValidationResult(BaseModel):
    """Complete email validation result."""

    email: str
    is_valid: bool
    checks: list[ValidationCheck]
    risk_score: float  # 0-1, higher = riskier
    risk_reasons: list[str]
    domain: str
    provider: str | None = None
    suggestion: str | None = None  # For typo corrections
    validated_at: datetime


# =============================================================================
# Known Data
# =============================================================================


# Common email typos
COMMON_TYPOS = {
    "gmial.com": "gmail.com",
    "gmal.com": "gmail.com",
    "gamil.com": "gmail.com",
    "gnail.com": "gmail.com",
    "gmail.co": "gmail.com",
    "gmail.con": "gmail.com",
    "outloo.com": "outlook.com",
    "outlok.com": "outlook.com",
    "outlook.co": "outlook.com",
    "hotmal.com": "hotmail.com",
    "hotmai.com": "hotmail.com",
    "hotmail.co": "hotmail.com",
    "yahooo.com": "yahoo.com",
    "yaho.com": "yahoo.com",
    "yahoo.co": "yahoo.com",
    "yhaoo.com": "yahoo.com",
    "icloud.co": "icloud.com",
    "iclod.com": "icloud.com",
}

# Disposable email domains (common ones)
DISPOSABLE_DOMAINS = {
    "10minutemail.com",
    "guerrillamail.com",
    "tempmail.com",
    "temp-mail.org",
    "throwaway.email",
    "mailinator.com",
    "maildrop.cc",
    "yopmail.com",
    "trashmail.com",
    "fakeinbox.com",
    "sharklasers.com",
    "dispostable.com",
    "getairmail.com",
    "mohmal.com",
    "tempail.com",
    "tempr.email",
    "discard.email",
    "spamgourmet.com",
    "mytemp.email",
    "getnada.com",
}

# Role-based email prefixes (often not read by individuals)
ROLE_BASED_PREFIXES = {
    "info",
    "support",
    "help",
    "sales",
    "contact",
    "admin",
    "administrator",
    "webmaster",
    "postmaster",
    "hostmaster",
    "abuse",
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "marketing",
    "hr",
    "careers",
    "jobs",
    "billing",
    "accounts",
    "team",
    "hello",
    "office",
    "mail",
    "enquiries",
    "enquiry",
    "feedback",
    "subscribe",
    "unsubscribe",
}

# Known major email providers
MAJOR_PROVIDERS = {
    "gmail.com": "Google",
    "googlemail.com": "Google",
    "outlook.com": "Microsoft",
    "hotmail.com": "Microsoft",
    "live.com": "Microsoft",
    "msn.com": "Microsoft",
    "yahoo.com": "Yahoo",
    "yahoo.co.uk": "Yahoo",
    "icloud.com": "Apple",
    "me.com": "Apple",
    "mac.com": "Apple",
    "aol.com": "AOL",
    "protonmail.com": "Proton",
    "proton.me": "Proton",
    "zoho.com": "Zoho",
}


# =============================================================================
# Email Validation Service
# =============================================================================


class EmailValidationService:
    """
    Validate email addresses before sending.

    Validation checks:
    1. Format validation (regex)
    2. Domain typo detection
    3. Disposable email detection
    4. Role-based email detection
    5. MX record verification
    6. Catch-all detection (optional, slower)
    """

    def __init__(self, db_session: AsyncSession | None = None):
        self.db = db_session

    async def validate(
        self,
        email: str,
        check_mx: bool = True,
        check_catch_all: bool = False,
    ) -> ValidationResult:
        """
        Validate an email address.

        Args:
            email: Email address to validate
            check_mx: Whether to verify MX records (DNS lookup)
            check_catch_all: Whether to check for catch-all domains (slower)

        Returns:
            ValidationResult with all check details
        """
        email = email.lower().strip()
        checks = []
        risk_reasons = []

        # Extract domain
        try:
            local_part, domain = email.split("@")
        except ValueError:
            return ValidationResult(
                email=email,
                is_valid=False,
                checks=[ValidationCheck(name="format", passed=False, reason="Missing @ symbol")],
                risk_score=1.0,
                risk_reasons=["Invalid format"],
                domain="",
                validated_at=datetime.utcnow(),
            )

        # 1. Format check
        format_check = self._check_format(email)
        checks.append(format_check)
        if not format_check.passed:
            return ValidationResult(
                email=email,
                is_valid=False,
                checks=checks,
                risk_score=1.0,
                risk_reasons=["Invalid email format"],
                domain=domain,
                validated_at=datetime.utcnow(),
            )

        # 2. Typo check
        typo_check, suggestion = self._check_typos(domain)
        checks.append(typo_check)
        if not typo_check.passed:
            risk_reasons.append("Possible domain typo")

        # 3. Disposable check
        disposable_check = self._check_disposable(domain)
        checks.append(disposable_check)
        if not disposable_check.passed:
            risk_reasons.append("Disposable email domain")

        # 4. Role-based check
        role_check = self._check_role_based(local_part)
        checks.append(role_check)
        if not role_check.passed:
            risk_reasons.append("Role-based email address")

        # 5. MX record check
        if check_mx:
            mx_check = await self._check_mx_record(domain)
            checks.append(mx_check)
            if not mx_check.passed:
                risk_reasons.append("No valid MX record")

        # Calculate overall validity
        critical_checks = ["format", "mx_record"]
        is_valid = all(
            c.passed for c in checks
            if c.name in critical_checks
        )

        # Calculate risk score
        risk_score = self._calculate_risk_score(checks, risk_reasons)

        # Get provider info
        provider = MAJOR_PROVIDERS.get(domain)

        return ValidationResult(
            email=email,
            is_valid=is_valid,
            checks=checks,
            risk_score=risk_score,
            risk_reasons=risk_reasons,
            domain=domain,
            provider=provider,
            suggestion=f"{local_part}@{suggestion}" if suggestion else None,
            validated_at=datetime.utcnow(),
        )

    async def validate_batch(
        self,
        emails: list[str],
        check_mx: bool = True,
    ) -> list[ValidationResult]:
        """
        Validate multiple email addresses.

        Uses asyncio.gather for concurrent MX lookups.
        """
        tasks = [self.validate(email, check_mx=check_mx) for email in emails]
        return await asyncio.gather(*tasks)

    def quick_validate(self, email: str) -> tuple[bool, str | None]:
        """
        Quick synchronous validation (format + typo only).

        Returns:
            Tuple of (is_valid, suggestion_or_error)
        """
        email = email.lower().strip()

        # Format check
        if not self._check_format(email).passed:
            return False, "Invalid email format"

        # Extract domain
        try:
            local_part, domain = email.split("@")
        except ValueError:
            return False, "Invalid email format"

        # Typo check
        if domain in COMMON_TYPOS:
            suggestion = f"{local_part}@{COMMON_TYPOS[domain]}"
            return False, f"Did you mean {suggestion}?"

        # Disposable check
        if domain in DISPOSABLE_DOMAINS:
            return False, "Disposable email addresses not allowed"

        return True, None

    # =========================================================================
    # Individual Checks
    # =========================================================================

    def _check_format(self, email: str) -> ValidationCheck:
        """Validate email format using regex."""
        # RFC 5322 compliant regex (simplified)
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

        if re.match(pattern, email):
            return ValidationCheck(name="format", passed=True)
        else:
            return ValidationCheck(
                name="format",
                passed=False,
                reason="Email does not match valid format",
            )

    def _check_typos(self, domain: str) -> tuple[ValidationCheck, str | None]:
        """Check for common domain typos."""
        if domain in COMMON_TYPOS:
            suggestion = COMMON_TYPOS[domain]
            return (
                ValidationCheck(
                    name="typo",
                    passed=False,
                    reason=f"Possible typo. Did you mean {suggestion}?",
                ),
                suggestion,
            )
        return ValidationCheck(name="typo", passed=True), None

    def _check_disposable(self, domain: str) -> ValidationCheck:
        """Check if domain is a known disposable email provider."""
        if domain in DISPOSABLE_DOMAINS:
            return ValidationCheck(
                name="disposable",
                passed=False,
                reason="Disposable email domain",
            )
        return ValidationCheck(name="disposable", passed=True)

    def _check_role_based(self, local_part: str) -> ValidationCheck:
        """Check if email is role-based (info@, support@, etc.)."""
        if local_part in ROLE_BASED_PREFIXES:
            return ValidationCheck(
                name="role_based",
                passed=False,
                reason=f"Role-based email prefix: {local_part}",
            )
        return ValidationCheck(name="role_based", passed=True)

    async def _check_mx_record(self, domain: str) -> ValidationCheck:
        """Verify domain has valid MX records."""
        try:
            # Use asyncio to run DNS lookup in thread pool
            loop = asyncio.get_event_loop()
            mx_records = await loop.run_in_executor(
                None,
                lambda: dns.resolver.resolve(domain, "MX"),
            )

            if mx_records:
                return ValidationCheck(name="mx_record", passed=True)
            else:
                return ValidationCheck(
                    name="mx_record",
                    passed=False,
                    reason="No MX records found",
                )

        except dns.resolver.NXDOMAIN:
            return ValidationCheck(
                name="mx_record",
                passed=False,
                reason="Domain does not exist",
            )
        except dns.resolver.NoAnswer:
            return ValidationCheck(
                name="mx_record",
                passed=False,
                reason="No MX records configured",
            )
        except dns.resolver.NoNameservers:
            return ValidationCheck(
                name="mx_record",
                passed=False,
                reason="No nameservers available",
            )
        except Exception as e:
            logger.warning(f"MX lookup failed for {domain}: {e}")
            # Return True on error to avoid blocking valid emails
            return ValidationCheck(
                name="mx_record",
                passed=True,
                reason="Could not verify (DNS timeout)",
            )

    def _calculate_risk_score(
        self,
        checks: list[ValidationCheck],
        risk_reasons: list[str],
    ) -> float:
        """
        Calculate overall risk score (0-1).

        Higher score = higher risk of bounce/spam.
        """
        score = 0.0

        # Critical failures
        for check in checks:
            if not check.passed:
                if check.name == "format":
                    score += 1.0  # Invalid format = max risk
                elif check.name == "mx_record":
                    score += 0.8  # No MX = very high risk
                elif check.name == "disposable":
                    score += 0.6  # Disposable = high risk
                elif check.name == "typo":
                    score += 0.5  # Typo = medium-high risk
                elif check.name == "role_based":
                    score += 0.2  # Role-based = lower engagement risk

        return min(1.0, score)


# =============================================================================
# Factory Function
# =============================================================================


def get_email_validation_service(
    db_session: AsyncSession | None = None,
) -> EmailValidationService:
    """Factory function to get EmailValidationService instance."""
    return EmailValidationService(db_session)
