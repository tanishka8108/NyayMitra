from fastapi import APIRouter
from database.connection import get_db_connection

router = APIRouter(
    prefix="/api/lawyers",
    tags=["Lawyers"]
)


@router.get("")
def get_lawyers():
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            lawyer_id,
            full_name,
            gender,
            years_of_experience,
            state,
            district,
            city,
            professional_email
        FROM lawyers
        ORDER BY lawyer_id
    """)

    rows = cursor.fetchall()

    cursor.close()
    connection.close()

    lawyers = []

    for row in rows:
        lawyers.append({
            "lawyer_id": row[0],
            "full_name": row[1],
            "gender": row[2],
            "years_of_experience": row[3],
            "state": row[4],
            "district": row[5],
            "city": row[6],
            "professional_email": row[7]
        })

    return {
        "count": len(lawyers),
        "lawyers": lawyers
    }