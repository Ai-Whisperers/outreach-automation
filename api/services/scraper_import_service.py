"""
Scraper Import Service.

Imports prospect data from company-webscraper JSON output into the outreach database.
Extracts decision makers, pain points, and personalization context.
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.outreach_models import (
    OutreachCampaign,
    Prospect,
    ProspectStatus,
)
from ..logging_config import get_logger

logger = get_logger("services.scraper_import")


class ScraperImportService:
    """
    Import prospects from webscraper JSON output.

    The webscraper produces comprehensive company intelligence including:
    - Company fundamentals
    - Decision maker contacts
    - Pain points from sentiment analysis
    - Competitive intelligence
    - Outreach talking points

    This service extracts actionable prospect data and creates enriched
    prospect records ready for personalized outreach.
    """

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def import_from_json(
        self,
        json_path: str | Path,
        campaign_id: int | None = None,
        skip_duplicates: bool = True,
        auto_start_sequence: bool = False,
    ) -> dict[str, Any]:
        """
        Import prospects from a single scraper JSON output file.

        Args:
            json_path: Path to the scraper JSON output
            campaign_id: Campaign to assign prospects to
            skip_duplicates: Skip if email already exists
            auto_start_sequence: Start email sequence immediately

        Returns:
            Import result with counts and details
        """
        result = {
            "success": False,
            "file_path": str(json_path),
            "prospects_found": 0,
            "prospects_imported": 0,
            "prospects_skipped": 0,
            "prospects_updated": 0,
            "errors": [],
        }

        try:
            # Load JSON
            path = Path(json_path)
            if not path.exists():
                result["errors"].append(f"File not found: {json_path}")
                return result

            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Extract prospects from scraper data
            prospects_data = self._extract_prospects(data)
            result["prospects_found"] = len(prospects_data)

            if not prospects_data:
                result["errors"].append("No decision makers found in scraper output")
                return result

            # Import each prospect
            for prospect_data in prospects_data:
                try:
                    import_status = await self._import_single_prospect(
                        prospect_data=prospect_data,
                        campaign_id=campaign_id,
                        skip_duplicates=skip_duplicates,
                        auto_start_sequence=auto_start_sequence,
                    )

                    if import_status == "imported":
                        result["prospects_imported"] += 1
                    elif import_status == "skipped":
                        result["prospects_skipped"] += 1
                    elif import_status == "updated":
                        result["prospects_updated"] += 1

                except Exception as e:
                    logger.error(f"Error importing prospect: {e}")
                    result["errors"].append(str(e))

            await self.db.commit()
            result["success"] = True

            logger.info(
                f"Import complete: {result['prospects_imported']} imported, "
                f"{result['prospects_skipped']} skipped, {result['prospects_updated']} updated"
            )

            return result

        except json.JSONDecodeError as e:
            result["errors"].append(f"Invalid JSON: {e}")
            return result
        except Exception as e:
            logger.error(f"Import error: {e}")
            result["errors"].append(str(e))
            return result

    async def import_from_directory(
        self,
        directory_path: str | Path,
        campaign_id: int | None = None,
        pattern: str = "*.json",
        skip_duplicates: bool = True,
    ) -> dict[str, Any]:
        """
        Import prospects from all JSON files in a directory.

        Args:
            directory_path: Path to directory containing scraper outputs
            campaign_id: Campaign to assign prospects to
            pattern: Glob pattern for JSON files
            skip_duplicates: Skip if email already exists

        Returns:
            Aggregated import results
        """
        result = {
            "success": False,
            "files_processed": 0,
            "total_prospects_found": 0,
            "total_prospects_imported": 0,
            "total_prospects_skipped": 0,
            "file_results": [],
            "errors": [],
        }

        try:
            path = Path(directory_path)
            if not path.exists() or not path.is_dir():
                result["errors"].append(f"Directory not found: {directory_path}")
                return result

            json_files = list(path.glob(pattern))

            if not json_files:
                result["errors"].append(f"No JSON files found matching pattern: {pattern}")
                return result

            for json_file in json_files:
                file_result = await self.import_from_json(
                    json_path=json_file,
                    campaign_id=campaign_id,
                    skip_duplicates=skip_duplicates,
                )

                result["files_processed"] += 1
                result["total_prospects_found"] += file_result["prospects_found"]
                result["total_prospects_imported"] += file_result["prospects_imported"]
                result["total_prospects_skipped"] += file_result["prospects_skipped"]
                result["file_results"].append({
                    "file": json_file.name,
                    "imported": file_result["prospects_imported"],
                    "skipped": file_result["prospects_skipped"],
                })

            result["success"] = True

            logger.info(
                f"Directory import complete: {result['files_processed']} files, "
                f"{result['total_prospects_imported']} prospects imported"
            )

            return result

        except Exception as e:
            logger.error(f"Directory import error: {e}")
            result["errors"].append(str(e))
            return result

    def _extract_prospects(self, scraper_data: dict) -> list[dict]:
        """
        Extract prospect records from scraper JSON output.

        Maps scraper fields to prospect model fields.
        """
        prospects = []

        # Get company info
        company_info = self._extract_company_info(scraper_data)

        # Extract decision makers
        decision_makers = scraper_data.get("decision_makers", [])

        # If no decision makers section, try alternative paths
        if not decision_makers:
            decision_makers = scraper_data.get("contacts", [])

        if not decision_makers:
            # Try to extract from executive team
            exec_team = scraper_data.get("leadership", {}).get("executive_team", [])
            decision_makers = exec_team

        for dm in decision_makers:
            prospect = self._map_decision_maker_to_prospect(dm, company_info, scraper_data)
            if prospect and prospect.get("email"):  # Must have email
                prospects.append(prospect)

        return prospects

    def _extract_company_info(self, data: dict) -> dict:
        """Extract company-level information from scraper data."""
        company = data.get("company", {})

        return {
            "company_name": company.get("name") or data.get("company_name"),
            "industry": company.get("industry") or data.get("industry"),
            "headquarters": company.get("headquarters") or data.get("headquarters"),
            "employee_count": company.get("employees", {}).get("global_count"),
            "revenue": company.get("revenue"),
            "website": company.get("website"),
        }

    def _map_decision_maker_to_prospect(
        self,
        dm: dict,
        company_info: dict,
        full_data: dict,
    ) -> dict | None:
        """
        Map a decision maker from scraper output to prospect data.

        Args:
            dm: Decision maker dict from scraper
            company_info: Extracted company info
            full_data: Full scraper output for enrichment

        Returns:
            Prospect data dict or None if invalid
        """
        # Extract name
        name = dm.get("name", "")
        name_parts = name.split(maxsplit=1) if name else ["", ""]
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        # Must have at least first name
        if not first_name:
            return None

        # Extract email (try multiple fields)
        email = (
            dm.get("email") or
            dm.get("email_guess") or
            dm.get("work_email")
        )

        # Clean email
        if email:
            email = email.lower().strip()

        # Build prospect data
        prospect = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "title": dm.get("title") or dm.get("role"),
            "company": company_info.get("company_name"),
            "industry": company_info.get("industry"),
            "location": dm.get("location") or company_info.get("headquarters"),
            "linkedin_url": dm.get("linkedin") or dm.get("linkedin_url"),
            "priority_tier": dm.get("priority") or self._determine_priority(dm, full_data),
            "company_size": company_info.get("employee_count"),
            "decision_maker_score": self._calculate_dm_score(dm),

            # Rich personalization data from scraper
            "personalization_data": self._build_personalization_data(dm, full_data),

            # Store full scraper data for reference
            "scraper_data": {
                "source_company": company_info.get("company_name"),
                "scoring": full_data.get("scoring", {}),
                "tier": full_data.get("scoring", {}).get("tier"),
            },
        }

        return prospect

    def _build_personalization_data(self, dm: dict, full_data: dict) -> dict:
        """
        Build rich personalization data from scraper output.

        This is the key data used for AI-powered message personalization.
        """
        sentiment = full_data.get("sentiment", {})
        outreach = full_data.get("outreach_materials", {})
        competitors = full_data.get("competitors", [])

        # Extract pain points from sentiment analysis
        pain_points = []
        top_complaints = sentiment.get("top_complaints", [])
        for complaint in top_complaints[:5]:
            if isinstance(complaint, dict):
                pain_points.append({
                    "category": complaint.get("category"),
                    "description": complaint.get("description"),
                    "severity": complaint.get("severity"),
                    "percentage": complaint.get("percentage"),
                })
            elif isinstance(complaint, str):
                pain_points.append({"description": complaint})

        # Extract talking points
        talking_points = outreach.get("talking_points", [])
        if isinstance(talking_points, str):
            talking_points = [talking_points]

        # Extract competitor names
        competitor_names = []
        for comp in competitors[:5]:
            if isinstance(comp, dict):
                competitor_names.append(comp.get("name"))
            elif isinstance(comp, str):
                competitor_names.append(comp)

        # Build personalization context
        return {
            "pain_points": pain_points,
            "talking_points": talking_points[:5],
            "competitors": [c for c in competitor_names if c],
            "sentiment_summary": {
                "positive_percent": sentiment.get("positive_percent"),
                "negative_percent": sentiment.get("negative_percent"),
                "overall": sentiment.get("overall"),
            },
            "recent_news": full_data.get("news", {}).get("recent", [])[:3],
            "service_fit": full_data.get("service_fit", {}),
            "deal_potential": full_data.get("deal_potential", {}),
            "email_hooks": outreach.get("email_subject_lines", []),
            "key_metrics": self._extract_key_metrics(full_data),
        }

    def _extract_key_metrics(self, data: dict) -> dict:
        """Extract key metrics for personalization."""
        company = data.get("company", {})
        social = data.get("digital_presence", {}).get("social_media", {})

        return {
            "employee_count": company.get("employees", {}).get("global_count"),
            "revenue": company.get("revenue"),
            "instagram_followers": social.get("instagram", {}).get("followers"),
            "monthly_comments": social.get("total_monthly_comments"),
            "stores_count": company.get("stores", {}).get("total"),
        }

    def _determine_priority(self, dm: dict, full_data: dict) -> str:
        """Determine prospect priority tier based on scoring."""
        scoring = full_data.get("scoring", {})
        tier = scoring.get("tier", "").lower()

        if tier in ["tier 1", "high", "priority"]:
            return "high"
        elif tier in ["tier 2", "medium"]:
            return "medium"
        else:
            return "low"

    def _calculate_dm_score(self, dm: dict) -> float:
        """Calculate decision maker score (0-1) based on role relevance."""
        title = (dm.get("title") or "").lower()

        # C-level executives
        if any(t in title for t in ["ceo", "cto", "cmo", "coo", "chief"]):
            return 1.0

        # VP level
        if any(t in title for t in ["vp", "vice president", "svp"]):
            return 0.9

        # Director level
        if "director" in title:
            return 0.8

        # Manager level
        if "manager" in title or "head of" in title:
            return 0.7

        # Lead level
        if "lead" in title or "senior" in title:
            return 0.6

        # Default
        return 0.5

    async def _import_single_prospect(
        self,
        prospect_data: dict,
        campaign_id: int | None,
        skip_duplicates: bool,
        auto_start_sequence: bool,
    ) -> str:
        """
        Import a single prospect record.

        Returns: "imported", "skipped", or "updated"
        """
        email = prospect_data.get("email")

        if not email:
            return "skipped"

        # Check for existing prospect
        stmt = select(Prospect).where(Prospect.email == email)
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            if skip_duplicates:
                return "skipped"
            else:
                # Update existing prospect with new data
                await self._update_prospect(existing, prospect_data)
                return "updated"

        # Create new prospect
        prospect = Prospect(
            campaign_id=campaign_id,
            email=email,
            first_name=prospect_data["first_name"],
            last_name=prospect_data.get("last_name", ""),
            title=prospect_data.get("title"),
            company=prospect_data.get("company"),
            industry=prospect_data.get("industry"),
            location=prospect_data.get("location"),
            linkedin_url=prospect_data.get("linkedin_url"),
            personalization_data=prospect_data.get("personalization_data"),
            scraper_data=prospect_data.get("scraper_data"),
            priority_tier=prospect_data.get("priority_tier"),
            company_size=prospect_data.get("company_size"),
            decision_maker_score=prospect_data.get("decision_maker_score"),
            enriched_at=datetime.utcnow(),
            status=ProspectStatus.RESEARCHED,  # Already has research data
        )

        self.db.add(prospect)

        logger.debug(f"Imported prospect: {email} ({prospect_data.get('company')})")

        return "imported"

    async def _update_prospect(self, prospect: Prospect, new_data: dict):
        """Update existing prospect with new scraper data."""
        # Update fields that might have changed
        if new_data.get("title"):
            prospect.title = new_data["title"]
        if new_data.get("company"):
            prospect.company = new_data["company"]
        if new_data.get("linkedin_url"):
            prospect.linkedin_url = new_data["linkedin_url"]

        # Merge personalization data
        if new_data.get("personalization_data"):
            existing_data = prospect.personalization_data or {}
            existing_data.update(new_data["personalization_data"])
            prospect.personalization_data = existing_data

        # Update scraper data
        if new_data.get("scraper_data"):
            prospect.scraper_data = new_data["scraper_data"]

        prospect.enriched_at = datetime.utcnow()


# =============================================================================
# Factory Function
# =============================================================================


def get_scraper_import_service(db_session: AsyncSession) -> ScraperImportService:
    """Factory function to get ScraperImportService instance."""
    return ScraperImportService(db_session)
