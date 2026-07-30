from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import CurrentUser, get_mfa_verified_user
from app.models.user import (
    ProfileFact,
    ProfileFactCreateRequest,
    ProfileResponse,
    ProfileUpdateRequest,
    Tone,
    UserProfile,
)
from app.services import firestore_client

router = APIRouter(prefix="/profile", tags=["profile"])


def _to_profile(uid: str, doc: dict) -> UserProfile:
    return UserProfile(
        uid=uid,
        display_name=doc.get("displayName"),
        tone=doc.get("tone") or Tone.friendly,
        created_at=doc.get("createdAt"),
    )


@router.get("", response_model=ProfileResponse)
async def get_profile(user: CurrentUser = Depends(get_mfa_verified_user)):
    doc = firestore_client.get_user_doc(user.uid)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    facts = firestore_client.list_profile_facts(user.uid)
    return ProfileResponse(
        profile=_to_profile(user.uid, doc),
        facts=[ProfileFact(id=f["id"], text=f["text"], created_at=f.get("createdAt")) for f in facts],
    )


@router.patch("", response_model=UserProfile)
async def update_profile(body: ProfileUpdateRequest, user: CurrentUser = Depends(get_mfa_verified_user)):
    firestore_client.update_user_profile(
        user.uid,
        display_name=body.display_name,
        tone=body.tone.value if body.tone else None,
    )
    doc = firestore_client.get_user_doc(user.uid)
    return _to_profile(user.uid, doc)


@router.post("/facts", response_model=ProfileFact, status_code=status.HTTP_201_CREATED)
async def add_fact(body: ProfileFactCreateRequest, user: CurrentUser = Depends(get_mfa_verified_user)):
    fact = firestore_client.add_profile_fact(user.uid, body.text)
    return ProfileFact(id=fact["id"], text=fact["text"], created_at=fact.get("createdAt"))


@router.delete("/facts/{fact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fact(fact_id: str, user: CurrentUser = Depends(get_mfa_verified_user)):
    firestore_client.delete_profile_fact(user.uid, fact_id)
