import json
from pathlib import Path

from ..config import DUPLICATE_REPORT_SIMILARITY
from ..models import BottleneckFlag, RawReport
from .client import generate_json
from .schemas import BottleneckExplanation, DuplicateVerdict, RecoveryNarrative

PROMPT_DIR = Path(__file__).parent / 'prompts'


def _prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding='utf-8')


async def judge_duplicate_reports(
    db,
    first: RawReport,
    second: RawReport,
    similarity: float,
) -> tuple[DuplicateVerdict, str]:
    first_data = {
        'text': first.text[:1000],
        'received_at': first.received_at.isoformat(),
        'sender_ref': first.sender_ref,
        'channel': first.channel,
    }
    second_data = {
        'text': second.text[:1000],
        'received_at': second.received_at.isoformat(),
        'sender_ref': second.sender_ref,
        'channel': second.channel,
    }

    def fallback() -> dict:
        same_sender = first.sender_ref is not None and first.sender_ref == second.sender_ref
        same_channel = first.channel == second.channel
        same_event = similarity >= DUPLICATE_REPORT_SIMILARITY or (similarity >= 0.82 and same_sender and same_channel)
        return {
            'same_event': same_event,
            'confidence': 'medium' if same_event else 'low',
            'rationale': 'Rule fallback based on text similarity, sender, and channel.',
        }

    result, source = await generate_json(
        db,
        task='duplicate_judge',
        prompt_version='duplicate_judge_v1',
        prompt=_prompt('duplicate_judge_v1.txt').format(
            first=json.dumps(first_data, separators=(',', ':')),
            second=json.dumps(second_data, separators=(',', ':')),
            similarity=round(similarity, 3),
        ),
        input_summary=json.dumps({'first': first_data, 'second': second_data, 'similarity': round(similarity, 3)}, separators=(',', ':')),
        schema=DuplicateVerdict,
        fallback=fallback,
    )
    return result, source


async def explain_bottleneck(db, flag: BottleneckFlag) -> tuple[BottleneckExplanation, str]:
    evidence = {
        'type': flag.flag_type,
        'severity': flag.severity,
        'evidence': flag.evidence,
        'current_explanation': flag.explanation,
        'current_suggested_action': flag.suggested_action,
    }

    def fallback() -> dict:
        return {'explanation': flag.explanation, 'suggested_action': flag.suggested_action}

    result, source = await generate_json(
        db,
        task='bottleneck_explainer',
        prompt_version='bottleneck_explainer_v1',
        prompt=_prompt('bottleneck_explainer_v1.txt').format(
            evidence=json.dumps(evidence, separators=(',', ':'))
        ),
        input_summary=json.dumps(evidence, separators=(',', ':')),
        schema=BottleneckExplanation,
        fallback=fallback,
    )
    return result, source


async def write_recovery_narrative(db, statistics: dict) -> tuple[RecoveryNarrative, str]:
    def fallback() -> dict:
        return {
            'narrative': (
                f"{statistics['reported_needs']['count']} reported needs; "
                f"{statistics['reported_needs']['remaining_quantity']} quantity remains; "
                f"{statistics['confirmed_assistance_quantity']} quantity is confirmed delivered. "
                'See the structured estimates and verified assessments for context.'
            ),
            'confidence': statistics['confidence'],
        }

    result, source = await generate_json(
        db,
        task='recovery_report',
        prompt_version='recovery_writer_v1',
        prompt=_prompt('recovery_writer_v1.txt').format(
            statistics=json.dumps(statistics, separators=(',', ':'))
        ),
        input_summary=json.dumps(statistics, separators=(',', ':')),
        schema=RecoveryNarrative,
        fallback=fallback,
    )
    return result, source
