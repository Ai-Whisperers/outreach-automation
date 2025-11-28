"""
Brand Brief Loader Service.

Parses markdown brand brief files and extracts structured data
for personalization in outreach messages.
"""

import re
from pathlib import Path
from typing import Any

from ..logging_config import get_logger

logger = get_logger("services.brand_brief_loader")


class BrandBriefLoader:
    """
    Load and parse brand brief markdown files for personalization.

    Brand briefs contain:
    - Company overview (name, industry, revenue, employees)
    - Service fit assessment
    - Key pain points
    - Key opportunities
    - Decision makers
    - Messaging strategy (value propositions, talking points, objection handling)
    """

    def __init__(self, brand_briefs_dir: Path | None = None):
        self.brand_briefs_dir = brand_briefs_dir or Path("../11-Brand-Briefs")

    def load_brief(self, brief_path: str | Path) -> dict[str, Any]:
        """
        Load and parse a brand brief from a file path.

        Args:
            brief_path: Path to the markdown file (relative or absolute)

        Returns:
            Parsed brand brief dictionary
        """
        path = Path(brief_path)

        # Handle relative paths
        if not path.is_absolute():
            path = self.brand_briefs_dir / path

        if not path.exists():
            logger.error(f"Brand brief not found: {path}")
            raise FileNotFoundError(f"Brand brief not found: {path}")

        content = path.read_text(encoding="utf-8")
        return self._parse_brief(content, str(path))

    def search_by_company(self, company_name: str) -> dict[str, Any] | None:
        """
        Search for a brand brief by company name.

        Args:
            company_name: Company name to search for

        Returns:
            Parsed brand brief or None if not found
        """
        if not self.brand_briefs_dir.exists():
            logger.warning(f"Brand briefs directory not found: {self.brand_briefs_dir}")
            return None

        # Normalize company name for matching
        normalized = self._normalize_name(company_name)

        # Search through all markdown files
        for brief_path in self.brand_briefs_dir.rglob("*.md"):
            brief_name = self._normalize_name(brief_path.stem)

            # Check for match
            if normalized in brief_name or brief_name in normalized:
                logger.info(f"Found brand brief for {company_name}: {brief_path}")
                return self.load_brief(brief_path)

        logger.info(f"No brand brief found for: {company_name}")
        return None

    def list_briefs(self) -> list[dict[str, str]]:
        """List all available brand briefs."""
        briefs = []

        if not self.brand_briefs_dir.exists():
            return briefs

        for brief_path in self.brand_briefs_dir.rglob("*.md"):
            # Extract company name from file
            content = brief_path.read_text(encoding="utf-8")
            company_name = self._extract_company_name(content) or brief_path.stem

            briefs.append(
                {
                    "path": str(brief_path.relative_to(self.brand_briefs_dir)),
                    "company_name": company_name,
                    "industry": brief_path.parent.name,
                }
            )

        return sorted(briefs, key=lambda x: x["company_name"])

    # =========================================================================
    # Brief Parsing
    # =========================================================================

    def _parse_brief(self, content: str, file_path: str) -> dict[str, Any]:
        """Parse a brand brief markdown file into structured data."""
        brief = {
            "file_path": file_path,
            "company_overview": {},
            "tier": None,
            "score": None,
            "digital_presence": {},
            "service_fit": {},
            "key_pain_points": [],
            "key_opportunities": [],
            "decision_makers": [],
            "messaging_strategy": {},
            "talking_points": [],
            "objection_handling": [],
            "discovery_questions": [],
            "sample_outreach": {},
            "deal_potential": {},
        }

        # Extract sections
        sections = self._split_sections(content)

        # Parse each section
        for section_title, section_content in sections.items():
            section_lower = section_title.lower()

            if "company overview" in section_lower:
                brief["company_overview"] = self._parse_overview_table(section_content)

            elif "priority" in section_lower or "tier" in section_lower:
                tier_match = re.search(r"TIER\s*(\d)", section_title, re.IGNORECASE)
                if tier_match:
                    brief["tier"] = int(tier_match.group(1))
                score_match = re.search(r"Score:\s*(\d+)/(\d+)", section_title)
                if score_match:
                    brief["score"] = {
                        "value": int(score_match.group(1)),
                        "max": int(score_match.group(2)),
                    }

            elif "digital presence" in section_lower:
                brief["digital_presence"] = self._parse_digital_presence(section_content)

            elif "service fit" in section_lower:
                brief["service_fit"] = self._parse_service_fit(section_content)

            elif "pain point" in section_lower:
                brief["key_pain_points"] = self._parse_numbered_list(section_content)

            elif "opportunity" in section_lower:
                brief["key_opportunities"] = self._parse_bullet_list(section_content)

            elif "decision maker" in section_lower:
                brief["decision_makers"] = self._parse_decision_makers(section_content)

            elif "messaging strategy" in section_lower:
                brief["messaging_strategy"] = self._parse_messaging_strategy(
                    section_content
                )

            elif "talking point" in section_lower:
                brief["talking_points"] = self._parse_talking_points(section_content)

            elif "objection" in section_lower:
                brief["objection_handling"] = self._parse_objection_handling(
                    section_content
                )

            elif "discovery question" in section_lower:
                brief["discovery_questions"] = self._parse_bullet_list(section_content)

            elif "sample" in section_lower and "outreach" in section_lower:
                brief["sample_outreach"] = self._parse_sample_outreach(section_content)

            elif "deal" in section_lower or "potential" in section_lower:
                brief["deal_potential"] = self._parse_deal_potential(section_content)

        # Extract company name if not in overview
        if "company_name" not in brief["company_overview"]:
            brief["company_overview"]["company_name"] = self._extract_company_name(
                content
            )

        return brief

    def _split_sections(self, content: str) -> dict[str, str]:
        """Split markdown content into sections by headers."""
        sections = {}
        current_section = "header"
        current_content = []

        for line in content.split("\n"):
            # Check for section header (## or ###)
            header_match = re.match(r"^#{2,3}\s+(.+)$", line)
            if header_match:
                # Save previous section
                if current_content:
                    sections[current_section] = "\n".join(current_content)
                current_section = header_match.group(1).strip()
                current_content = []
            else:
                current_content.append(line)

        # Save last section
        if current_content:
            sections[current_section] = "\n".join(current_content)

        return sections

    def _parse_overview_table(self, content: str) -> dict[str, str]:
        """Parse company overview table."""
        overview = {}

        # Parse markdown table rows
        for line in content.split("\n"):
            # Look for table rows: | **Field** | Value |
            match = re.match(r"\|\s*\*?\*?([^|*]+)\*?\*?\s*\|\s*([^|]+)\s*\|", line)
            if match:
                field = match.group(1).strip().lower().replace(" ", "_")
                value = match.group(2).strip()

                # Skip header row
                if field != "field" and value != "details" and "---" not in value:
                    overview[field] = value

        return overview

    def _parse_digital_presence(self, content: str) -> dict[str, Any]:
        """Parse digital presence section."""
        presence = {"social_media": [], "metrics": {}}

        # Parse social media table
        in_social_table = False
        for line in content.split("\n"):
            if "platform" in line.lower() and "|" in line:
                in_social_table = True
                continue

            if in_social_table and "|" in line and "---" not in line:
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 2:
                    presence["social_media"].append(
                        {
                            "platform": parts[0],
                            "followers": parts[1] if len(parts) > 1 else "",
                            "engagement": parts[2] if len(parts) > 2 else "",
                        }
                    )

            # Parse digital metrics (bullet points)
            metric_match = re.match(r"-\s*\*\*(.+)\*\*:\s*(.+)", line)
            if metric_match:
                key = metric_match.group(1).strip().lower().replace(" ", "_")
                presence["metrics"][key] = metric_match.group(2).strip()

        return presence

    def _parse_service_fit(self, content: str) -> dict[str, Any]:
        """Parse service fit assessment section."""
        fit = {"comment_analyzer": {}, "training": {}, "key_use_cases": []}

        # Extract ratings
        rating_match = re.search(
            r"Comment Analyzer Need:\s*(\d)/(\d)", content, re.IGNORECASE
        )
        if rating_match:
            fit["comment_analyzer"]["rating"] = f"{rating_match.group(1)}/{rating_match.group(2)}"

        training_match = re.search(
            r"Training.*Need:\s*(\d)/(\d)", content, re.IGNORECASE
        )
        if training_match:
            fit["training"]["rating"] = f"{training_match.group(1)}/{training_match.group(2)}"

        # Extract key use cases
        in_use_cases = False
        for line in content.split("\n"):
            if "key use cases" in line.lower():
                in_use_cases = True
                continue
            if in_use_cases and line.strip().startswith("-"):
                fit["key_use_cases"].append(line.strip().lstrip("- "))
            elif in_use_cases and line.strip().startswith("#"):
                in_use_cases = False

        return fit

    def _parse_numbered_list(self, content: str) -> list[str]:
        """Parse numbered list (1. Item, 2. Item, etc.)."""
        items = []
        for line in content.split("\n"):
            match = re.match(r"^\d+\.\s*\*?\*?(.+?)\*?\*?\s*[-–]?\s*(.*)", line)
            if match:
                item = match.group(1).strip()
                description = match.group(2).strip() if match.group(2) else ""
                if description:
                    items.append(f"{item}: {description}")
                else:
                    items.append(item)
        return items

    def _parse_bullet_list(self, content: str) -> list[str]:
        """Parse bullet list (- Item or * Item)."""
        items = []
        for line in content.split("\n"):
            match = re.match(r"^[-*]\s+\*?\*?(.+)", line)
            if match:
                items.append(match.group(1).strip().rstrip("*"))
        return items

    def _parse_decision_makers(self, content: str) -> list[dict[str, str]]:
        """Parse decision makers section."""
        makers = []

        # Parse table rows
        for line in content.split("\n"):
            # Skip headers
            if "role" in line.lower() and "|" in line:
                continue
            if "---" in line:
                continue

            # Parse table row
            if "|" in line:
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 2:
                    makers.append(
                        {
                            "role": parts[0],
                            "search_strategy": parts[1] if len(parts) > 1 else "",
                            "priority": parts[2] if len(parts) > 2 else "MEDIUM",
                        }
                    )

        return makers

    def _parse_messaging_strategy(self, content: str) -> dict[str, Any]:
        """Parse messaging strategy section."""
        strategy = {"value_propositions": {}, "competitive_angle": "", "roi_statements": []}

        # Extract value propositions (quoted text after audience headers)
        audience_pattern = re.compile(
            r"\*\*For ([^:]+):\*\*\s*\n>\s*\"?(.+?)\"?(?=\n\n|\*\*For|\Z)",
            re.DOTALL,
        )
        for match in audience_pattern.finditer(content):
            audience = match.group(1).strip()
            proposition = match.group(2).strip().strip('">')
            strategy["value_propositions"][audience] = proposition

        # Extract competitive angle
        comp_match = re.search(
            r"Competitive Angle\*?\*?\s*\n>\s*\"?(.+?)\"?(?=\n\n|###|\Z)",
            content,
            re.DOTALL,
        )
        if comp_match:
            strategy["competitive_angle"] = comp_match.group(1).strip().strip('">')

        # Extract ROI statements
        in_roi = False
        for line in content.split("\n"):
            if "roi statement" in line.lower():
                in_roi = True
                continue
            if in_roi and line.strip().startswith("-"):
                strategy["roi_statements"].append(line.strip().lstrip("- ").strip('"'))
            elif in_roi and (line.strip().startswith("#") or line.strip().startswith("**")):
                in_roi = False

        return strategy

    def _parse_talking_points(self, content: str) -> list[dict[str, str]]:
        """Parse talking points section."""
        points = []

        # Extract opening hooks
        hook_pattern = re.compile(r'\d+\.\s*"(.+?)"', re.DOTALL)
        for match in hook_pattern.finditer(content):
            points.append({"type": "opening_hook", "content": match.group(1).strip()})

        return points

    def _parse_objection_handling(self, content: str) -> list[dict[str, str]]:
        """Parse objection handling table."""
        objections = []

        for line in content.split("\n"):
            if "---" in line or "objection" in line.lower():
                continue

            if "|" in line:
                parts = [p.strip().strip('"') for p in line.split("|") if p.strip()]
                if len(parts) >= 2:
                    objections.append(
                        {
                            "objection": parts[0],
                            "response": parts[1] if len(parts) > 1 else "",
                            "follow_up": parts[2] if len(parts) > 2 else "",
                        }
                    )

        return objections

    def _parse_sample_outreach(self, content: str) -> dict[str, str]:
        """Parse sample outreach email section."""
        outreach = {"subject": "", "body": ""}

        # Extract subject line
        subject_match = re.search(r"Subject:\s*\"?(.+?)\"?\s*\n", content)
        if subject_match:
            outreach["subject"] = subject_match.group(1).strip()

        # Extract body (everything after subject until next section)
        body_match = re.search(
            r"Subject:.+?\n\n(.+?)(?=\n---|\n##|\Z)", content, re.DOTALL
        )
        if body_match:
            outreach["body"] = body_match.group(1).strip()

        return outreach

    def _parse_deal_potential(self, content: str) -> dict[str, Any]:
        """Parse deal potential section."""
        potential = {}

        # Look for monetary values
        money_pattern = re.compile(r"\$[\d,]+(?:K|M)?(?:/year)?", re.IGNORECASE)
        for match in money_pattern.finditer(content):
            potential["revenue_potential"] = match.group(0)
            break

        # Look for ROI
        roi_match = re.search(r"(\d+)x\s*return", content, re.IGNORECASE)
        if roi_match:
            potential["roi_multiplier"] = f"{roi_match.group(1)}x"

        # Look for sales cycle
        cycle_match = re.search(r"(\d+-?\d*)\s*months?", content, re.IGNORECASE)
        if cycle_match:
            potential["sales_cycle"] = f"{cycle_match.group(1)} months"

        return potential

    def _extract_company_name(self, content: str) -> str | None:
        """Extract company name from brief header."""
        match = re.search(r"#\s*BRAND BRIEF:\s*(.+?)(?:\(|$|\n)", content)
        if match:
            return match.group(1).strip()
        return None

    def _normalize_name(self, name: str) -> str:
        """Normalize name for matching."""
        # Remove common suffixes
        name = re.sub(
            r"\s+(inc|llc|ltd|corp|co|company|corporation|latam|global)\.?$",
            "",
            name,
            flags=re.IGNORECASE,
        )
        # Convert to lowercase, remove non-alphanumeric
        return re.sub(r"[^a-z0-9]", "", name.lower())

    # =========================================================================
    # Personalization Context Extraction
    # =========================================================================

    def get_personalization_context(
        self, brief: dict[str, Any], prospect_role: str | None = None
    ) -> dict[str, Any]:
        """
        Extract personalization context from a brand brief.

        Returns structured data for message personalization:
        - company_name
        - industry
        - pain_points (top 3)
        - value_proposition (role-specific if available)
        - key_metrics
        - competitor_insights
        - talking_points
        """
        context = {
            "company_name": brief.get("company_overview", {}).get("company_name", ""),
            "industry": brief.get("company_overview", {}).get("industry", ""),
            "revenue": brief.get("company_overview", {}).get("revenue", ""),
            "employees": brief.get("company_overview", {}).get("employees", ""),
            "pain_points": brief.get("key_pain_points", [])[:3],
            "opportunities": brief.get("key_opportunities", [])[:3],
            "value_proposition": "",
            "key_metrics": [],
            "talking_points": [],
            "decision_makers": brief.get("decision_makers", []),
        }

        # Get role-specific value proposition
        messaging = brief.get("messaging_strategy", {})
        value_props = messaging.get("value_propositions", {})

        if prospect_role and value_props:
            # Try to match role to a value proposition
            role_lower = prospect_role.lower()
            for audience, prop in value_props.items():
                if any(
                    keyword in role_lower
                    for keyword in audience.lower().split("/")
                ):
                    context["value_proposition"] = prop
                    break

        # If no role match, use first value proposition
        if not context["value_proposition"] and value_props:
            context["value_proposition"] = list(value_props.values())[0]

        # Extract key metrics from digital presence
        digital = brief.get("digital_presence", {})
        metrics = digital.get("metrics", {})
        for key, value in metrics.items():
            context["key_metrics"].append(f"{key.replace('_', ' ').title()}: {value}")

        # Add talking points/hooks
        for point in brief.get("talking_points", []):
            if isinstance(point, dict):
                context["talking_points"].append(point.get("content", ""))
            else:
                context["talking_points"].append(str(point))

        # Add competitive angle if available
        if messaging.get("competitive_angle"):
            context["competitive_angle"] = messaging["competitive_angle"]

        return context

    def extract_pain_points(self, brief: dict[str, Any]) -> list[str]:
        """Extract pain points from brand brief."""
        return brief.get("key_pain_points", [])

    def extract_metrics(self, brief: dict[str, Any]) -> dict[str, str]:
        """Extract key metrics from brand brief."""
        metrics = {}

        # From company overview
        overview = brief.get("company_overview", {})
        if overview.get("revenue"):
            metrics["revenue"] = overview["revenue"]
        if overview.get("employees"):
            metrics["employees"] = overview["employees"]

        # From digital presence
        digital = brief.get("digital_presence", {})
        metrics.update(digital.get("metrics", {}))

        return metrics

    def get_decision_makers(self, brief: dict[str, Any]) -> list[dict[str, str]]:
        """Get decision maker contacts from brand brief."""
        return brief.get("decision_makers", [])

    def get_icp_type(self, brief: dict[str, Any]) -> str:
        """
        Determine ICP type from brand brief.

        Returns: 'solopreneur', 'sme', or 'enterprise'
        """
        tier = brief.get("tier")
        overview = brief.get("company_overview", {})

        # Check tier first
        if tier and tier <= 2:
            return "enterprise"
        elif tier and tier >= 4:
            return "solopreneur"

        # Check revenue/employees
        revenue_str = overview.get("revenue", "")
        employees_str = overview.get("employees", "")

        # Parse revenue (look for B for billion, M for million)
        if "B" in revenue_str.upper() or "billion" in revenue_str.lower():
            return "enterprise"
        elif "M" in revenue_str.upper() or "million" in revenue_str.lower():
            # Check if > 50M
            match = re.search(r"[\$€]?([\d.]+)\s*M", revenue_str, re.IGNORECASE)
            if match and float(match.group(1)) >= 50:
                return "enterprise"
            return "sme"

        # Parse employees
        emp_match = re.search(r"([\d,]+)\+?", employees_str)
        if emp_match:
            emp_count = int(emp_match.group(1).replace(",", ""))
            if emp_count >= 200:
                return "enterprise"
            elif emp_count >= 10:
                return "sme"
            else:
                return "solopreneur"

        return "sme"  # Default


def get_brand_brief_loader(brand_briefs_dir: Path | None = None) -> BrandBriefLoader:
    """Factory function to get BrandBriefLoader instance."""
    return BrandBriefLoader(brand_briefs_dir)
