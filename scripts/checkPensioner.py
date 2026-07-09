import psycopg2
import time
import sys
import re
from extractingPensioner import Prosocour
from config import DB_CONFIG

TIME_BETWEEN_EACH_CALL = 0.5

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

def extractBirthYearFromHit(hit):
    """Extracts the 4-digit birth year from the specific JSON path in Prosocour's response."""
    try:
        source = hit.get("source", {})
        naissance = source.get("naissance", {})
        dateInfo = naissance.get("date", {})
        dateStr = dateInfo.get("date", "")
        
        if dateStr:
            # search for 4 number followinf each other
            match = re.search(r'\d{4}', str(dateStr))
            if match:
                return int(match.group())
    except (AttributeError, TypeError):
        pass
    
    return None

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

def evaluatePermutations(provider, name, surname, acceptableYears):
    """
    Splits composed names and executes an advanced search for every possible combination.
    Returns the total matches found, the number of permutations attempted, and the highest score.
    """
    nameParts = [part for part in re.split(r'[-\s]', name) if part]
    surnameParts = [part for part in re.split(r'[-\s]', surname) if part]
    
    # Abort if no first name exists or if neither name nor surname is composed
    if not name or (len(nameParts) <= 1 and len(surnameParts) <= 1):
        return 0, 0, 0.0 # return of permFound, permNb, permScore
        
    permNb = 0
    permFound = 0
    permScore = 0.0
    
    for n in nameParts:
        for s in surnameParts:
            permNb += 1
            time.sleep(TIME_BETWEEN_EACH_CALL)
            
            # Use strictly advanced search for permutations
            results = provider.fetch(query=None, name=n, surname=s)
            matchCount = len(results)
            
            if matchCount > 0:
                permFound += matchCount
                yearMatched = False
                
                # Verify birth year tolerance
                if acceptableYears:
                    for hit in results:
                        hitYear = extractBirthYearFromHit(hit)
                        if hitYear in acceptableYears:
                            permScore = max(permScore, 0.15)
                            yearMatched = True
                            break
                            
                # Base permutation score if year is missing or does not match
                if not yearMatched:
                    permScore = max(permScore, 0.05)
    
    # The final permutation score decreases in inverse proportion to the number of permutations attempted.
    # Formula: Final Score = Base Score / Total Permutations
    if permNb > 0:
        permScore = permScore / permNb

    return permFound, permNb, permScore

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
        time.sleep(TIME_BETWEEN_EACH_CALL)
        resultsAdv = providerProsocour.fetch(query=None, name=p['name'], surname=p['surname'])
        matchAdv = len(resultsAdv)
        
        # Simple Search
        time.sleep(TIME_BETWEEN_EACH_CALL)
        querySimple = f"{p['name']} {p['surname']}".strip()
        resultsSim = providerProsocour.fetch(query=querySimple)
        matchSim = len(resultsSim)
        
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

        #Permutation (for each case found)
        # 0.15: Permutation advanced match confirmed by birth year.
        # 0.05: Permutation advanced match, no birth year confirmation.
        
        score = 0.0
        dbYear = p['birth_year']
        yearMatched = False
        
        if dbYear is not None:
            try:
                baseYear = int(dbYear)
                acceptableYears = [baseYear - 1, baseYear, baseYear + 1]
                
                # Check advanced hits by extracting the exact year from the JSON path
                for hit in resultsAdv:
                    hitYear = extractBirthYearFromHit(hit)
                    if hitYear in acceptableYears:
                        score = 1.0 if matchAdv == 1 else 0.8
                        yearMatched = True
                        break 
                        
                # Check simple hits by extracting the exact year from the JSON path
                if not yearMatched:
                    for hit in resultsSim:
                        hitYear = extractBirthYearFromHit(hit)
                        if hitYear in acceptableYears:
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
        
        # Execute permutations only if primary search yields a score of 0.0
        if score == 0.0:
            permFound, permNb, permScore = evaluatePermutations(providerProsocour, p['name'], p['surname'], acceptableYears)
            
            if permNb > 0:
                if permFound > 0:
                    foundCount += 1
                print(f"{iteration} : {p['class']} : {p['name']} {p['surname']} : permFound={permFound} permNb={permNb} : sco={permScore}")
                continue # Skip the standard print format below

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