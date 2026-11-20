"""
Response Validation Module

CRITICAL: This module contains NO LLM calls.
All validation is algorithmic and deterministic.
"""
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """Result of validating a response"""
    valid: bool
    numeric_value: Optional[int] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    is_critical: bool = False
    critical_message: Optional[str] = None


class ResponseValidator:
    """
    Validates Likert scale responses without LLM.

    This class handles:
    1. Range validation for numeric responses
    2. Parsing text labels to numeric values
    3. Critical item detection
    4. Generating appropriate warnings
    """

    def validate_numeric_response(self, item, value: int) -> ValidationResult:
        """
        Validate a numeric Likert response.

        Args:
            item: ScaleItem instance
            value: Numeric response value

        Returns:
            ValidationResult with validation status
        """
        errors = []
        warnings = []
        is_critical = False
        critical_message = None

        # Range check
        if value < item.min_value:
            errors.append(
                f"Response {value} is below minimum value {item.min_value}"
            )
        elif value > item.max_value:
            errors.append(
                f"Response {value} is above maximum value {item.max_value}"
            )

        # Critical item check
        if item.is_critical and item.critical_threshold is not None:
            if value >= item.critical_threshold:
                is_critical = True
                critical_message = (
                    f"Response to critical item (Q{item.item_number}) "
                    f"is at or above threshold ({value} >= {item.critical_threshold}). "
                    f"Assessment flagged for professional review."
                )
                warnings.append(critical_message)

        return ValidationResult(
            valid=len(errors) == 0,
            numeric_value=value if len(errors) == 0 else None,
            errors=errors,
            warnings=warnings,
            is_critical=is_critical,
            critical_message=critical_message
        )

    def parse_likert_response(self, item, user_input: str) -> Optional[int]:
        """
        Parse a user input (numeric or label text) to a numeric value.

        Args:
            item: ScaleItem instance with response_options
            user_input: Raw user input string

        Returns:
            Numeric value if parseable, None otherwise
        """
        user_input = user_input.strip()

        # Try parsing as integer directly
        try:
            value = int(user_input)
            if item.min_value <= value <= item.max_value:
                return value
        except ValueError:
            pass

        # Try matching against labels
        response_options = item.response_options
        if isinstance(response_options, list):
            user_lower = user_input.lower()

            for option in response_options:
                if isinstance(option, dict):
                    label = option.get('label', '').lower()
                    value = option.get('value')

                    # Exact match
                    if user_lower == label:
                        return value

                    # Partial match (user input is contained in label)
                    if user_lower in label or label in user_lower:
                        return value

        return None

    def validate_and_parse(self, item, user_input: str) -> ValidationResult:
        """
        Parse and validate a user input in one step.

        Args:
            item: ScaleItem instance
            user_input: Raw user input string

        Returns:
            ValidationResult with parsed value if valid
        """
        # First try to parse
        numeric_value = self.parse_likert_response(item, user_input)

        if numeric_value is None:
            # Build helpful error message
            options_text = self._format_options(item)
            return ValidationResult(
                valid=False,
                errors=[
                    f"Could not understand response '{user_input}'. "
                    f"Please respond with a number ({item.min_value}-{item.max_value}) "
                    f"or one of: {options_text}"
                ]
            )

        # Then validate the parsed value
        return self.validate_numeric_response(item, numeric_value)

    def _format_options(self, item) -> str:
        """Format response options for display"""
        options = item.response_options
        if isinstance(options, list):
            labels = []
            for opt in options:
                if isinstance(opt, dict) and 'label' in opt:
                    labels.append(opt['label'])
            return ', '.join(labels)
        return 'available options'

    def check_response_consistency(
        self,
        session,
        new_response_value: int,
        new_item
    ) -> List[str]:
        """
        Check if a new response is consistent with previous responses.

        This performs basic consistency checks without LLM:
        - Extreme score swings within the same scale
        - All max or all min responses (potential invalid responding)

        Args:
            session: AssessmentSession instance
            new_response_value: The new response value
            new_item: The ScaleItem for the new response

        Returns:
            List of warning messages (empty if consistent)
        """
        from assessments.models import ScaleResponse

        warnings = []

        # Get previous responses for the same scale
        previous_responses = ScaleResponse.objects.filter(
            session=session,
            item__scale=new_item.scale
        )

        if previous_responses.count() < 2:
            # Not enough data for consistency check
            return warnings

        # Check for all-same responding
        all_values = [r.numeric_value for r in previous_responses]
        all_values.append(new_response_value)

        if len(set(all_values)) == 1 and len(all_values) >= 5:
            warnings.append(
                f"All responses on {new_item.scale.code} have been the same value ({all_values[0]}). "
                f"This pattern may indicate invalid responding."
            )

        # Check for extreme variance (alternating min/max)
        extremes = [new_item.min_value, new_item.max_value]
        extreme_count = sum(1 for v in all_values if v in extremes)
        if extreme_count == len(all_values) and len(all_values) >= 4:
            warnings.append(
                f"All responses on {new_item.scale.code} have been extreme values. "
                f"This pattern may indicate random or careless responding."
            )

        return warnings


class DistressDetector:
    """
    Detects distress signals in free-text responses.

    This is a simple keyword-based detector (no LLM) for safety-critical content.
    """

    # Keywords indicating potential crisis
    CRISIS_KEYWORDS = [
        'suicide', 'suicidal', 'kill myself', 'end my life',
        'self-harm', 'cut myself', 'hurt myself', 'die',
        'death wish', 'want to die', 'better off dead',
        'no reason to live', 'can\'t go on'
    ]

    # Keywords indicating significant distress
    DISTRESS_KEYWORDS = [
        'hopeless', 'worthless', 'hate myself',
        'can\'t take it', 'everyone would be better without me',
        'no point', 'give up', 'burden'
    ]

    def check_free_text(self, text: str) -> Dict[str, Any]:
        """
        Check free text for distress signals.

        Args:
            text: Free text response

        Returns:
            Dict with detection results
        """
        text_lower = text.lower()

        # Check for crisis keywords
        crisis_found = []
        for keyword in self.CRISIS_KEYWORDS:
            if keyword in text_lower:
                crisis_found.append(keyword)

        # Check for distress keywords
        distress_found = []
        for keyword in self.DISTRESS_KEYWORDS:
            if keyword in text_lower:
                distress_found.append(keyword)

        is_crisis = len(crisis_found) > 0
        is_distress = len(distress_found) > 0

        severity = 'none'
        if is_crisis:
            severity = 'crisis'
        elif is_distress:
            severity = 'distress'

        return {
            'has_distress_signal': is_crisis or is_distress,
            'is_crisis': is_crisis,
            'severity': severity,
            'crisis_keywords': crisis_found,
            'distress_keywords': distress_found,
            'requires_immediate_review': is_crisis,
            'requires_review': is_crisis or is_distress,
            'message': self._get_message(severity)
        }

    def _get_message(self, severity: str) -> str:
        if severity == 'crisis':
            return (
                "URGENT: Response contains crisis indicators. "
                "Assessment flagged for immediate professional review."
            )
        elif severity == 'distress':
            return (
                "Response contains distress indicators. "
                "Assessment flagged for professional review."
            )
        return "No significant distress signals detected."


# Singleton instances
response_validator = ResponseValidator()
distress_detector = DistressDetector()
