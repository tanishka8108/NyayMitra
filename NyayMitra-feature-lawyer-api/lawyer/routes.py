import psycopg2
from fastapi import APIRouter, HTTPException, Query

from database.connection import get_db_connection
from database.sqlite_db import connect as sqlite_connect

router = APIRouter(prefix="/api/lawyers", tags=["Lawyers"])


def split_semicolon_list(value):
    """Convert the DB's semicolon-separated text fields into JSON arrays."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(";") if item.strip()]


# lawyers.verification_status (the account database) rendered in the
# vocabulary the frontend's profile-status slot already speaks — see
# VerificationState in frontend/src/api/lawyerApi.ts. Unknown values
# pass through unchanged.
_PROFILE_STATUS = {
    "APPROVED": "Verified",
    "PENDING": "Pending",
    "REJECTED": "Rejected",
}


@router.get("")
def get_lawyers(
    name: str | None = None,
    city: str | None = None,
    district: str | None = None,
    state: str | None = None,
    practice_area: str | None = None,
    min_experience: int | None = Query(None, ge=0),
    max_experience: int | None = Query(None, ge=0),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    if min_experience is not None and max_experience is not None and min_experience > max_experience:
        raise HTTPException(
            status_code=400,
            detail="min_experience cannot be greater than max_experience.",
        )

    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        try:
            where_clause = """
                FROM lawyers l
                LEFT JOIN lawyer_practice_area lpa
                    ON l.lawyer_id = lpa.lawyer_id
                LEFT JOIN practice_area_master pam
                    ON lpa.practice_area_id = pam.practice_area_id
                WHERE 1 = 1
            """

            parameters = []

            if name and name.strip():
                where_clause += " AND LOWER(l.full_name) LIKE LOWER(%s)"
                parameters.append(f"%{name.strip()}%")

            if city and city.strip():
                where_clause += " AND LOWER(l.city) = LOWER(%s)"
                parameters.append(city.strip())

            if district and district.strip():
                where_clause += " AND LOWER(l.district) = LOWER(%s)"
                parameters.append(district.strip())

            if state and state.strip():
                where_clause += " AND LOWER(l.state) = LOWER(%s)"
                parameters.append(state.strip())

            if practice_area and practice_area.strip():
                where_clause += " AND LOWER(pam.practice_area_name) = LOWER(%s)"
                parameters.append(practice_area.strip())

            if min_experience is not None:
                where_clause += " AND l.years_of_experience >= %s"
                parameters.append(min_experience)

            if max_experience is not None:
                where_clause += " AND l.years_of_experience <= %s"
                parameters.append(max_experience)

            count_query = "SELECT COUNT(DISTINCT l.lawyer_id) " + where_clause
            cursor.execute(count_query, parameters)
            total_count = cursor.fetchone()[0]

            offset = (page - 1) * limit

            query = """
                SELECT DISTINCT
                    l.lawyer_id,
                    l.full_name,
                    l.gender,
                    l.years_of_experience,
                    l.state,
                    l.district,
                    l.city,
                    l.professional_email
            """ + where_clause + """
                ORDER BY l.lawyer_id
                LIMIT %s OFFSET %s
            """

            cursor.execute(query, parameters + [limit, offset])
            rows = cursor.fetchall()
        finally:
            cursor.close()
    finally:
        connection.close()

    lawyers = [
        {
            "lawyer_id": row[0],
            "full_name": row[1],
            "gender": row[2],
            "years_of_experience": row[3],
            "state": row[4],
            "district": row[5],
            "city": row[6],
            "professional_email": row[7],
        }
        for row in rows
    ]

    total_pages = (total_count + limit - 1) // limit if total_count else 0

    return {
        "count": len(lawyers),
        "total_count": total_count,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "lawyers": lawyers,
    }


@router.get("/{lawyer_id}")
def get_lawyer_profile(lawyer_id: str):
    lawyer_id = lawyer_id.strip()
    if not lawyer_id:
        raise HTTPException(status_code=400, detail="Lawyer ID is required.")

    # The legacy directory lives in PostgreSQL (lawyer_database.sql),
    # which this environment cannot run — see database/sqlite_db.py.
    # The Lawyer Dashboard must not die with it: when the directory
    # database is unreachable, serve the same response shape from the
    # account database, where every registered lawyer exists.
    try:
        return _profile_from_postgres(lawyer_id)
    except psycopg2.Error:
        return _profile_from_sqlite(lawyer_id)


def _profile_from_postgres(lawyer_id: str):
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                SELECT
                    l.lawyer_id,
                    l.full_name,
                    l.profile_photo,
                    l.profile_image,
                    l.gender,
                    l.date_of_birth,
                    l.enrollment_number,
                    l.registration_number,
                    l.bar_id_or_bar_code,
                    l.bar_council,
                    l.year_of_enrollment,
                    l.years_of_experience,
                    l.courts_of_practice,
                    l.state,
                    l.district,
                    l.city,
                    l.office_address,
                    l.pincode,
                    l.professional_phone_number,
                    l.professional_email,
                    l.office_phone,
                    l.website,
                    l.preferred_contact_method,
                    l.education_qualifications,
                    l.languages_known,
                    l.working_office_hours,
                    l.professional_bio,
                    l.data_source,
                    l.profile_status,
                    l.created_at,
                    l.updated_at
                FROM lawyers l
                WHERE l.lawyer_id = %s
                """,
                (lawyer_id,),
            )

            row = cursor.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Lawyer not found")

            cursor.execute(
                """
                SELECT pam.practice_area_name
                FROM lawyer_practice_area lpa
                JOIN practice_area_master pam
                    ON lpa.practice_area_id = pam.practice_area_id
                WHERE lpa.lawyer_id = %s
                ORDER BY pam.practice_area_name
                """,
                (lawyer_id,),
            )
            practice_area_rows = cursor.fetchall()
        finally:
            cursor.close()
    finally:
        connection.close()

    return {
        "lawyer_id": row[0],
        "full_name": row[1],
        "profile_photo": row[2],
        "profile_image": row[3],
        "gender": row[4],
        "date_of_birth": row[5].isoformat() if row[5] else None,
        "enrollment_number": row[6],
        "registration_number": row[7],
        "bar_id_or_bar_code": row[8],
        "bar_council": row[9],
        "year_of_enrollment": row[10],
        "years_of_experience": row[11],
        "practice_areas": [item[0] for item in practice_area_rows if item[0]],
        "courts_of_practice": split_semicolon_list(row[12]),
        "state": row[13],
        "district": row[14],
        "city": row[15],
        "office_address": row[16],
        "pincode": row[17],
        "professional_phone_number": row[18],
        "professional_email": row[19],
        "office_phone": row[20],
        "website": row[21],
        "preferred_contact_method": row[22],
        "education_qualifications": split_semicolon_list(row[23]),
        "languages_known": split_semicolon_list(row[24]),
        "working_office_hours": row[25],
        "professional_bio": row[26],
        "data_source": row[27],
        "profile_status": row[28],
        "created_at": row[29].isoformat() if row[29] else None,
        "updated_at": row[30].isoformat() if row[30] else None,
    }


def _profile_from_sqlite(lawyer_id: str):
    """Serve ``GET /{lawyer_id}`` from the account database.

    Fallback used when PostgreSQL is unreachable: this environment
    has no PostgreSQL at all (Phase 0 finding), while every lawyer
    registered through ``/api/auth/register/lawyer`` lives in the one
    project database (SQLite). The dict mirrors the PostgreSQL
    response key-for-key so the frontend needs no special case;
    columns the account database does not hold come back ``None`` /
    ``[]`` and the dashboard renders its usual "Not available".

    Deliberately exposes no login email: this route is public and
    ``users.email`` is a sign-in identity, not a professional
    contact address (the chat directory makes the same call).
    """
    connection = sqlite_connect()
    try:
        row = connection.execute(
            """
            SELECT
                l.lawyer_id,
                u.name,
                l.license_id,
                l.practice_areas,
                l.bar_council,
                l.years_of_experience,
                l.professional_phone_number,
                l.professional_bio,
                l.verification_status,
                l.created_at,
                l.updated_at
            FROM lawyers l
            JOIN users u ON u.id = l.user_id
            WHERE l.lawyer_id = ?
            """,
            (lawyer_id,),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        raise HTTPException(status_code=404, detail="Lawyer not found")

    return {
        "lawyer_id": row["lawyer_id"],
        "full_name": row["name"],
        "profile_photo": None,
        "profile_image": None,
        "gender": None,
        "date_of_birth": None,
        "enrollment_number": row["license_id"],
        "registration_number": None,
        "bar_id_or_bar_code": None,
        "bar_council": row["bar_council"],
        "year_of_enrollment": None,
        "years_of_experience": row["years_of_experience"],
        "practice_areas": split_semicolon_list(row["practice_areas"]),
        "courts_of_practice": [],
        "state": None,
        "district": None,
        "city": None,
        "office_address": None,
        "pincode": None,
        "professional_phone_number": row["professional_phone_number"],
        "professional_email": None,
        "office_phone": None,
        "website": None,
        "preferred_contact_method": None,
        "education_qualifications": [],
        "languages_known": [],
        "working_office_hours": None,
        "professional_bio": row["professional_bio"],
        "data_source": None,
        "profile_status": _PROFILE_STATUS.get(row["verification_status"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
