from __future__ import annotations
from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import Session
from webapp.config import settings
from webapp.models import Participant,Consent
from webapp.security import hash_secret,verify_secret

def bootstrap_invites(db: Session) -> None:
    for item in settings.invite_codes.split(","):
        if ":" not in item:
            continue
        label, code = (part.strip() for part in item.split(":", 1))
        if not label or not code:
            continue
        participant = db.scalar(select(Participant).where(Participant.label == label))
        if participant is None:
            db.add(Participant(label=label, invite_hash=hash_secret(code)))
        elif not verify_secret(participant.invite_hash, code):
            participant.invite_hash = hash_secret(code)
            participant.is_active = True
    db.commit()


def authenticate_invite(db: Session, code: str) -> Optional[Participant]:
    participants = db.scalars(select(Participant).where(Participant.is_active.is_(True))).all()
    for participant in participants:
        if verify_secret(participant.invite_hash, code):
            return participant
    return None


def has_current_consent(db: Session, participant_id: str) -> bool:
    return db.scalar(
        select(Consent.id).where(
            Consent.participant_id == participant_id,
            Consent.version == settings.consent_version,
        )
    ) is not None


def record_consent(db: Session, participant_id: str) -> Consent:
    existing = db.scalar(
        select(Consent).where(
            Consent.participant_id == participant_id,
            Consent.version == settings.consent_version,
        )
    )
    if existing:
        return existing
    consent = Consent(participant_id=participant_id, version=settings.consent_version)
    db.add(consent)
    db.commit()
    db.refresh(consent)
    return consent

