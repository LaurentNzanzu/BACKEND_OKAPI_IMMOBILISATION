from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session
from ...core.database import get_db
from ...core.security import get_current_user
from ...services.permission_service import PermissionService
from ...services.organisation_profil_service import OrganisationProfilService, MAX_LOGO_BYTES
from ...schemas.organisation_profil import OrganisationProfilResponse, OrganisationProfilUpdate

router = APIRouter(prefix="/organisations/me", tags=["Profil organisation"])


def profile_admin(user=Depends(get_current_user), db: Session = Depends(get_db)):
    role = (user.role.nom if user.role else "").upper()
    if user.organisation_id is None or role != "ADMIN" or not PermissionService(db).hasPermission(user, "ORGANISATION_GERER"):
        raise HTTPException(403, "Vous n’êtes pas autorisé à modifier cette organisation.")
    return user


@router.get("/profil", response_model=OrganisationProfilResponse)
def get_profile(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return OrganisationProfilService(db).current(user)


@router.patch("/profil", response_model=OrganisationProfilResponse)
def patch_profile(payload: OrganisationProfilUpdate, request: Request,
                  db: Session = Depends(get_db), user=Depends(profile_admin)):
    return OrganisationProfilService(db).update(user, payload.model_dump(exclude_unset=True), request)


@router.post("/logo", response_model=OrganisationProfilResponse)
def upload_logo(request: Request, file: UploadFile = File(...),
                db: Session = Depends(get_db), user=Depends(profile_admin)):
    content = file.file.read(MAX_LOGO_BYTES + 1)
    return OrganisationProfilService(db).upload(user, content, request)


@router.delete("/logo", response_model=OrganisationProfilResponse)
def delete_logo(request: Request, db: Session = Depends(get_db), user=Depends(profile_admin)):
    return OrganisationProfilService(db).delete_logo(user, request)
