"""
Summary Verification Module - Hallucination Prevention

This module fact-checks LLM-generated summaries against stored data.
CRITICAL: All verification is algorithmic (NO LLM calls).
"""
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from django.utils import timezone


@dataclass
class VerificationResult:
    """Result of verifying a summary"""
    is_valid: bool
    errors: List[str] = field(default_factory=list)  # Hard errors (hallucinations)
    warnings: List[str] = field(default_factory=list)  # Soft warnings
    score_claims: List[Dict] = field(default_factory=list)  # Extracted score claims
    severity_claims: List[Dict] = field(default_factory=list)  # Extracted severity claims
    quote_claims: List[Dict] = field(default_factory=list)  # Extracted quotes


class SummaryVerifier:
    """
    Fact-checks LLM summaries against stored data.

    This class is responsible for:
    1. Extracting factual claims from summary text
    2. Verifying score mentions against ScaleScore records
    3. Verifying severity level claims
    4. Verifying quoted text against stored responses
    5. Flagging invented symptoms not measured by scales
    """

    # Patterns for extracting claims from text
    SCORE_PATTERNS = [
        # "PHQ-9: 15" or "PHQ-9 score: 15" or "PHQ-9 = 15"
        r'(PHQ[-\s]?9|GAD[-\s]?7|PSS[-\s]?10|ISI)[\s:=]+(\d+)',
        # "scored 15 on the PHQ-9"
        r'scored?\s+(\d+)\s+on\s+(?:the\s+)?(PHQ[-\s]?9|GAD[-\s]?7|PSS[-\s]?10|ISI)',
        # "PHQ-9 score of 15"
        r'(PHQ[-\s]?9|GAD[-\s]?7|PSS[-\s]?10|ISI)\s+score\s+of\s+(\d+)',
        # "total score: 15" (after scale name mentioned)
        r'total\s+score[\s:=]+(\d+)',
    ]

    SEVERITY_PATTERNS = [
        # "PHQ-9 indicates moderate depression"
        r'(PHQ[-\s]?9|GAD[-\s]?7|PSS[-\s]?10|ISI)\s+indicates?\s+(minimal|mild|moderate|moderately\s+severe|severe)',
        # "moderate depression" or "severe anxiety"
        r'(minimal|mild|moderate|moderately\s+severe|severe)\s+(depression|anxiety|stress|insomnia)',
        # "severity: moderate" or "severity level: moderate"
        r'severity[\s:]+(?:level[\s:]+)?(minimal|mild|moderate|moderately\s+severe|severe)',
    ]

    # Map scale codes to their variations
    SCALE_CODE_MAP = {
        'PHQ9': ['PHQ-9', 'PHQ 9', 'PHQ9'],
        'GAD7': ['GAD-7', 'GAD 7', 'GAD7'],
        'PSS10': ['PSS-10', 'PSS 10', 'PSS10'],
        'ISI': ['ISI'],
    }

    # Map scale types to keywords
    SCALE_TYPE_MAP = {
        'depression': 'PHQ9',
        'anxiety': 'GAD7',
        'stress': 'PSS10',
        'insomnia': 'ISI',
        'sleep': 'ISI',
    }

    def verify(self, session, summary_text: str) -> VerificationResult:
        """
        Main verification method - fact-checks the summary.

        Args:
            session: AssessmentSession instance
            summary_text: LLM-generated summary text

        Returns:
            VerificationResult with errors and warnings
        """
        errors = []
        warnings = []
        score_claims = []
        severity_claims = []
        quote_claims = []

        # 1. Verify score claims
        score_errors, score_data = self._verify_score_claims(session, summary_text)
        errors.extend(score_errors)
        score_claims = score_data

        # 2. Verify severity claims
        severity_errors, severity_data = self._verify_severity_claims(session, summary_text)
        errors.extend(severity_errors)
        severity_claims = severity_data

        # 3. Verify quotes
        quote_errors, quote_warnings, quote_data = self._verify_quotes(session, summary_text)
        errors.extend(quote_errors)
        warnings.extend(quote_warnings)
        quote_claims = quote_data

        # 4. Check for invented symptoms
        invented_warnings = self._check_invented_symptoms(session, summary_text)
        warnings.extend(invented_warnings)

        return VerificationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            score_claims=score_claims,
            severity_claims=severity_claims,
            quote_claims=quote_claims
        )

    def _verify_score_claims(
        self,
        session,
        summary_text: str
    ) -> Tuple[List[str], List[Dict]]:
        """
        Extract and verify score mentions in the summary.

        Returns:
            Tuple of (errors list, claims list)
        """
        from assessments.models import ScaleScore

        errors = []
        claims = []

        # Get actual scores from database
        actual_scores = {}
        for score in ScaleScore.objects.filter(session=session).select_related('scale'):
            actual_scores[score.scale.code] = score.total_score

        # Extract score claims from text
        summary_upper = summary_text.upper()

        for pattern in self.SCORE_PATTERNS:
            matches = re.finditer(pattern, summary_text, re.IGNORECASE)
            for match in matches:
                groups = match.groups()

                # Determine scale code and claimed score from match groups
                scale_code = None
                claimed_score = None

                for g in groups:
                    if g is None:
                        continue
                    if g.upper() in ['PHQ-9', 'PHQ 9', 'PHQ9']:
                        scale_code = 'PHQ9'
                    elif g.upper() in ['GAD-7', 'GAD 7', 'GAD7']:
                        scale_code = 'GAD7'
                    elif g.upper() in ['PSS-10', 'PSS 10', 'PSS10']:
                        scale_code = 'PSS10'
                    elif g.upper() == 'ISI':
                        scale_code = 'ISI'
                    elif g.isdigit():
                        claimed_score = int(g)

                if scale_code and claimed_score is not None:
                    claim = {
                        'scale': scale_code,
                        'claimed_score': claimed_score,
                        'match_text': match.group(0)
                    }

                    # Verify against actual
                    if scale_code in actual_scores:
                        actual = actual_scores[scale_code]
                        claim['actual_score'] = actual
                        claim['verified'] = (claimed_score == actual)

                        if claimed_score != actual:
                            errors.append(
                                f"HALLUCINATION: Summary claims {scale_code} score is {claimed_score}, "
                                f"but actual score is {actual}"
                            )
                    else:
                        claim['actual_score'] = None
                        claim['verified'] = False
                        errors.append(
                            f"HALLUCINATION: Summary mentions {scale_code} score ({claimed_score}), "
                            f"but this scale was not administered or has no score"
                        )

                    claims.append(claim)

        return errors, claims

    def _verify_severity_claims(
        self,
        session,
        summary_text: str
    ) -> Tuple[List[str], List[Dict]]:
        """
        Extract and verify severity level claims.

        Returns:
            Tuple of (errors list, claims list)
        """
        from assessments.models import ScaleScore

        errors = []
        claims = []

        # Get actual severities
        actual_severities = {}
        for score in ScaleScore.objects.filter(session=session).select_related('scale'):
            actual_severities[score.scale.code] = score.severity_level

        # Normalize severity terms
        def normalize_severity(sev: str) -> str:
            sev = sev.lower().replace(' ', '_')
            if sev == 'moderately_severe':
                return 'moderately_severe'
            return sev

        for pattern in self.SEVERITY_PATTERNS:
            matches = re.finditer(pattern, summary_text, re.IGNORECASE)
            for match in matches:
                groups = match.groups()

                scale_code = None
                claimed_severity = None

                for g in groups:
                    if g is None:
                        continue
                    g_upper = g.upper().replace(' ', '')
                    g_lower = g.lower()

                    # Check if it's a scale name
                    if g_upper in ['PHQ-9', 'PHQ9', 'PHQ 9']:
                        scale_code = 'PHQ9'
                    elif g_upper in ['GAD-7', 'GAD7', 'GAD 7']:
                        scale_code = 'GAD7'
                    elif g_upper in ['PSS-10', 'PSS10', 'PSS 10']:
                        scale_code = 'PSS10'
                    elif g_upper == 'ISI':
                        scale_code = 'ISI'
                    # Check if it's a condition (map to scale)
                    elif g_lower == 'depression':
                        scale_code = 'PHQ9'
                    elif g_lower == 'anxiety':
                        scale_code = 'GAD7'
                    elif g_lower == 'stress':
                        scale_code = 'PSS10'
                    elif g_lower in ['insomnia', 'sleep']:
                        scale_code = 'ISI'
                    # Check if it's a severity term
                    elif g_lower in ['minimal', 'mild', 'moderate', 'moderately severe', 'severe']:
                        claimed_severity = normalize_severity(g_lower)

                if scale_code and claimed_severity:
                    claim = {
                        'scale': scale_code,
                        'claimed_severity': claimed_severity,
                        'match_text': match.group(0)
                    }

                    if scale_code in actual_severities:
                        actual = actual_severities[scale_code]
                        claim['actual_severity'] = actual
                        claim['verified'] = (claimed_severity == actual)

                        if claimed_severity != actual:
                            errors.append(
                                f"HALLUCINATION: Summary claims {scale_code} severity is "
                                f"'{claimed_severity}', but actual severity is '{actual}'"
                            )
                    else:
                        claim['actual_severity'] = None
                        claim['verified'] = False

                    claims.append(claim)

        return errors, claims

    def _verify_quotes(
        self,
        session,
        summary_text: str
    ) -> Tuple[List[str], List[str], List[Dict]]:
        """
        Verify that quoted text exists in stored responses.

        Returns:
            Tuple of (errors list, warnings list, claims list)
        """
        from assessments.models import ScaleResponse, FreeTextResponse

        errors = []
        warnings = []
        claims = []

        # Extract quoted text (single or double quotes)
        quote_pattern = r'["\']([^"\']{10,})["\']'
        matches = re.finditer(quote_pattern, summary_text)

        # Get all stored text
        stored_texts = set()

        # From scale responses (verbatim text)
        for response in ScaleResponse.objects.filter(session=session):
            if response.verbatim_text:
                stored_texts.add(response.verbatim_text.lower())

        # From free text responses
        for response in FreeTextResponse.objects.filter(session=session):
            stored_texts.add(response.response_text.lower())

        for match in matches:
            quoted_text = match.group(1)
            quoted_lower = quoted_text.lower()

            claim = {
                'quoted_text': quoted_text,
                'found_in_responses': False
            }

            # Check if quote exists in any stored text
            found = False
            for stored in stored_texts:
                if quoted_lower in stored or stored in quoted_lower:
                    found = True
                    break

            claim['found_in_responses'] = found

            if not found:
                # Check for close matches (some words match)
                quoted_words = set(quoted_lower.split())
                best_overlap = 0
                for stored in stored_texts:
                    stored_words = set(stored.split())
                    overlap = len(quoted_words & stored_words)
                    if overlap > best_overlap:
                        best_overlap = overlap

                if best_overlap < len(quoted_words) * 0.5:
                    # Less than 50% word overlap - likely fabricated
                    errors.append(
                        f"HALLUCINATION: Quote '{quoted_text[:50]}...' does not appear "
                        f"in any stored responses"
                    )
                else:
                    warnings.append(
                        f"Quote '{quoted_text[:50]}...' may be paraphrased from responses"
                    )

            claims.append(claim)

        return errors, warnings, claims

    def _check_invented_symptoms(
        self,
        session,
        summary_text: str
    ) -> List[str]:
        """
        Check for symptoms mentioned that weren't measured.

        Returns:
            List of warnings
        """
        warnings = []

        # Symptoms not covered by PHQ-9, GAD-7, PSS-10, ISI
        UNMEASURED_CONDITIONS = [
            ('psychosis', 'psychotic symptoms'),
            ('hallucination', 'hallucinations'),
            ('delusion', 'delusional thinking'),
            ('mania', 'manic symptoms'),
            ('bipolar', 'bipolar symptoms'),
            ('ptsd', 'PTSD symptoms'),
            ('trauma', 'trauma symptoms'),
            ('ocd', 'OCD symptoms'),
            ('obsessive', 'obsessive symptoms'),
            ('compulsive', 'compulsive behaviors'),
            ('eating disorder', 'eating disorder symptoms'),
            ('anorexia', 'anorexia symptoms'),
            ('bulimia', 'bulimia symptoms'),
            ('substance', 'substance use'),
            ('addiction', 'addiction'),
            ('alcohol', 'alcohol use'),
            ('drug', 'drug use'),
        ]

        summary_lower = summary_text.lower()

        # Get administered scales
        administered_scales = set(
            session.assigned_scales.values_list('code', flat=True)
        )

        for keyword, condition_name in UNMEASURED_CONDITIONS:
            if keyword in summary_lower:
                warnings.append(
                    f"Summary mentions '{condition_name}', but this was not "
                    f"measured by the administered scales ({', '.join(administered_scales)}). "
                    f"This should be verified with appropriate assessment."
                )

        return warnings

    def save_verification_results(
        self,
        session,
        result: VerificationResult
    ) -> None:
        """
        Save verification results to the GroundedSummary.

        Args:
            session: AssessmentSession instance
            result: VerificationResult to save
        """
        from assessments.models import GroundedSummary

        try:
            summary = GroundedSummary.objects.get(session=session)
            summary.is_verified = result.is_valid
            summary.verification_errors = result.errors
            summary.verification_warnings = result.warnings
            summary.verification_timestamp = timezone.now()

            # Extract cited quotes that were verified
            summary.cited_quotes = [
                claim['quoted_text']
                for claim in result.quote_claims
                if claim.get('found_in_responses', False)
            ]

            summary.save()
        except GroundedSummary.DoesNotExist:
            pass


# Singleton instance
summary_verifier = SummaryVerifier()
