from fastapi import APIRouter
from database.connection import get_db_connection

practice_area_router = APIRouter(
    prefix="/api/practice-areas",
    tags=["Practice Areas"]
)


@practice_area_router.get("")
def get_practice_areas():
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            practice_area_id,
            practice_area_name,
            description
        FROM practice_area_master
        ORDER BY practice_area_id
    """)

    rows = cursor.fetchall()

    cursor.close()
    connection.close()

    practice_areas = []

    for row in rows:
        practice_areas.append({
            "practice_area_id": row[0],
            "practice_area_name": row[1],
            "description": row[2]
        })

    return {
        "count": len(practice_areas),
        "practice_areas": practice_areas
    }
