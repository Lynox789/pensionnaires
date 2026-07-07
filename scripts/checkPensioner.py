import psycopg2
import time
import sys
from extractingPensioner import Prosocour
from config import DB_CONFIG

def fetchPensioner():
    """Retrieve 20 pensioners for each class from 1 to 7."""
    query = """
    SELECT id, class, last_name, first_name
    FROM (
        SELECT id, class, last_name, first_name,
               ROW_NUMBER() OVER (PARTITION BY class ORDER BY id) as rn
        FROM pensionnaires
        WHERE class BETWEEN 1 AND 7
    ) sub
    WHERE rn <= 20
    ORDER BY class, id;
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        
        pensionnaires = []
        for row in rows:
            pensionnaires.append({
                "surname": row[2].strip() if row[2] else "",
                "name": row[3].strip() if row[3] else "",
                "class": row[1]
            })
        cursor.close()
        conn.close()
        return pensionnaires
    except Exception as e:
        print(f"Database connection error: {e}")
        sys.exit(1)

def main():
    # Init of Prosocour provider
    provider = Prosocour()
    
    print("Retrieving pensioners from database...")
    pensionnaires = fetchPensioner()
    total_count = len(pensionnaires)
    
    print(f"Processing {total_count} records...\n")
    found_count = 0

    for p in pensionnaires:
        # sleep 1 sec
        time.sleep(1)
        
        #using fetch method from Prosocour class
        results = provider.fetch(query=None, name=p['name'], surname=p['surname'])
        match_count = len(results)
        
        if match_count > 0:
            found_count += 1
            
        print(f"Class {p['class']} {p['name']} {p['surname']} : {match_count} match(es)")

    # Final summary
    success_rate = (found_count / total_count) * 100 if total_count > 0 else 0
    
    print("Process finished")
    print(f"Total processed: {total_count}")
    print(f"Pensioners with at least one record: {found_count}")
    print(f"Success rate: {success_rate:.2f}%")

if __name__ == "__main__":
    main()