import json
import re
from typing import Any


def robust_json_parse(response: str, logger) -> dict[str, Any]:
    """
    Robustly parse JSON from LLM response, handling extra text and markdown.

    Args:
        response: Raw response from LLM
        logger: Logger instance for warnings/errors

    Returns:
        Parsed JSON as dict

    Raises:
        ValueError: If no valid JSON could be extracted
    """
    # Remove markdown code blocks if present
    content = response.strip()
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]

    content = content.strip()

    # Try direct parse first (fastest path)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # If direct parse fails, try to extract JSON from response
        logger.warning("Direct JSON parse failed, attempting extraction...")

        # Try to find JSON object (starts with {, ends with })
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            try:
                extracted = json_match.group()
                parsed = json.loads(extracted)
                logger.info("Successfully extracted JSON object from response")
                return parsed
            except json.JSONDecodeError:
                pass

        # Try to find JSON array (starts with [, ends with ])
        array_match = re.search(r"\[.*\]", content, re.DOTALL)
        if array_match:
            try:
                extracted = array_match.group()
                parsed = json.loads(extracted)
                logger.info("Successfully extracted JSON array from response")
                return parsed
            except json.JSONDecodeError:
                pass

        # If all extraction attempts fail, raise error
        logger.error(f"Failed to parse JSON after all extraction attempts")
        logger.debug(f"Response was: {response[:500]}")
        raise ValueError("Could not extract valid JSON from response")


# Example usage in generate_json method:
# Replace this line:
#     return json.loads(content.strip())
#
# With this:
#     return robust_json_parse(response, logger)
