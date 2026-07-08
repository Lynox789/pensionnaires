import psycopg2
import time
import sys
import json
from extractingPensioner import Prosocour
from config import DB_CONFIG

def cleanText(text):
    """Cleans specific prefixes and suffixes from a given text."""
    if not text:
        return ""
    
    text = text.strip()
    
    prefixesToRemove = ["fr. ", "fr.", "de ", "d' ", "d'"]
    suffixesToRemove = [" de", " d'"]
    
    for prefix in prefixesToRemove:
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
            break 
            
    for suffix in suffixesToRemove:
        if text.lower().endswith(suffix):
            text = text[:-len(suffix)]
            break

    return text.strip()

def fetchPensioner():
    """Retrieve 20 pensioners for each class from 1 to 7, including birth year."""
    query = """
    SELECT id, class, last_name, first_name, birth_year
    FROM (
        SELECT id, class, COALESCE(last_name, '') AS last_name, COALESCE(first_name, '') AS first_name,
               birth_year,
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
                "surname": cleanText(row[2]),
                "name": cleanText(row[3]),
                "class": row[1],
                "birth_year": row[4] 
            })
        cursor.close()
        conn.close()
        return pensionnaires
    except Exception as e:
        print(f"Database connection error: {e}")
        sys.exit(1)

def main():
    # Init of Prosocour provider
    providerProsocour = Prosocour()
    
    print("Retrieving pensioners from database...")
    pensionnaires = fetchPensioner()
    totalCount = len(pensionnaires)
    
    print(f"Processing {totalCount} records...\n")
    
    iteration = 0
    foundCount = 0
    
    for p in pensionnaires:
        iteration += 1
        
        # Advanced Search
        time.sleep(1)
        resultsAdv = providerProsocour.fetch(query=None, name=p['name'], surname=p['surname'])
        matchAdv = len(resultsAdv) #count how many results we have
        
        # Simple Search
        time.sleep(1)
        querySimple = f"{p['name']} {p['surname']}".strip()
        resultsSim = providerProsocour.fetch(query=querySimple)
        matchSim = len(resultsSim) #count how many results we have
        
        if matchAdv > 0 or matchSim > 0:
            foundCount += 1

        # Scoring System:
        # 1.0 : Single advanced match confirmed by birth year (+/- 1 year).
        # 0.8 : Multiple advanced matches, but one is confirmed by birth year.
        # 0.7 : Single advanced match, but birth year is missing or doesn't match.
        # 0.6 : Simple match confirmed by birth year.
        # 0.5 : Multiple advanced matches, no birth year confirmation.
        # 0.3 : Simple match only, no birth year confirmation.
        # 0.0 : No matches found.
        
        score = 0.0
        dbYear = p['birth_year']
        yearMatched = False
        
        if dbYear is not None:
            try:
                baseYear = int(dbYear)
                # Define tolerance: [year-1, year, year+1]
                acceptableYears = [str(baseYear - 1), str(baseYear), str(baseYear + 1)]
                
                # Check if ANY of the acceptable years exist in the JSON data of the advanced hits
                for hit in resultsAdv:
                    hitJson = json.dumps(hit)
                    if any(y in hitJson for y in acceptableYears):
                        score = 1.0 if matchAdv == 1 else 0.8
                        yearMatched = True
                        break 
                        
                # If not found in advanced, check in the simple hits
                if not yearMatched:
                    for hit in resultsSim:
                        hitJson = json.dumps(hit)
                        if any(y in hitJson for y in acceptableYears):
                            score = 0.6
                            yearMatched = True
                            break
            except ValueError:
                pass 
                
        # Apply fallback scores if the birth year was not matched or missing
        if not yearMatched:
            if matchAdv == 1:
                score = 0.7 
            elif matchAdv > 1:
                score = 0.5 
            elif matchSim > 0:
                score = 0.3 

        # Final Output Formatting
        print(f"{iteration} : {p['class']} : {p['name']} {p['surname']} : adv={matchAdv} sim={matchSim} : sco={score}")

    # Final summary
    successRate = (foundCount / totalCount) * 100 if totalCount > 0 else 0
    print("\nProcess finished")
    print(f"Total processed: {totalCount}")
    print(f"Pensioners with at least one record: {foundCount}")
    print(f"Success rate: {successRate:.2f}%")

if __name__ == "__main__":
    main()