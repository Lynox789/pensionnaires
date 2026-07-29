import psycopg2
import time
import sys
import re
from extractingPensioner import Prosocour
from config import DB_CONFIG

TIME_BETWEEN_EACH_CALL = 0.5
MAX_AUTHORITY_LINKS_PER_PERMUTATION = 10
MAX_PERMUTATIONS_PER_PENSIONER = 8

#Variable to clean first and lastname
WORDS_TO_ERASE = {"de", "du", "des", "la", "le", "les", "l", "d"}
TITLES_PATTERN = re.compile(
    r'\b(baronne|baron|comte|comtesse|cte|princesse|prince|dlle|demoiselle|dame|anonyme|filleul|veuve|duc|duchesse|marquis|marquise)\b', 
    re.IGNORECASE
)

def cleanText(text):
    """Cleans specific prefixes and suffixes from a given text."""
    if not text:
        return ""
    
    text = text.strip()
    
    # Remove titles and descriptions using regex
    text = TITLES_PATTERN.sub('', text).strip()
    
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
    SELECT id, class, last_name, first_name, birth_year, uid
    FROM (
        SELECT id, class, COALESCE(last_name, '') AS last_name, COALESCE(first_name, '') AS first_name,
               birth_year, uid,
               ROW_NUMBER() OVER (PARTITION BY class ORDER BY id) as rn
        FROM pensionnaires
        WHERE class BETWEEN 1 AND 7
    ) sub
    WHERE rn <= 1
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
                "birth_year": row[4],
                "uid": row[5]
            })
        cursor.close()
        conn.close()
        return pensionnaires
    except Exception as e:
        print(f"Database connection error: {e}")
        sys.exit(1)

def evaluatePermutations(provider, name, surname, acceptableYears):
    """
    Splits composed names, filters stop words, and executes an advanced search for combinations.
    Handles cases where the first name is missing by cross-referencing all available name parts.
    """
    # Split and filter out noise words like
    nameParts = [part for part in re.split(r'[-\s]', name) if part and part.lower() not in WORDS_TO_ERASE]
    surnameParts = [part for part in re.split(r'[-\s]', surname) if part and part.lower() not in WORDS_TO_ERASE]
    
    # Merge into a single pool to handle cases where the first name is missing or swapped
    allParts = nameParts + surnameParts
    
    # Abort if we don't have at least two meaningful words to permute
    if len(allParts) < 2:
        return 0, 0, 0.0, []
        
    permNb = 0
    permFound = 0
    permScore = 0.0
    collectedHits = []

    # Try every valid word combination
    for i, n in enumerate(allParts):
        for j, s in enumerate(allParts):
            if i == j: # Prevent searching the exact same word against itself
                continue
                
            if permNb >= MAX_PERMUTATIONS_PER_PENSIONER:
                break

            permNb += 1
            time.sleep(TIME_BETWEEN_EACH_CALL)
            
            # Use strictly advanced search for permutations
            results = provider.fetch(query=None, name=n, surname=s)
            matchCount = len(results)
            
            if matchCount > 0:
                permFound += matchCount
                collectedHits.extend(results)
                yearMatched = False
                
                # Verify birth year tolerance
                if acceptableYears:
                    for hit in results:
                        hitYear = extractBirthYearFromHit(hit)
                        if hitYear in acceptableYears:
                            permScore = max(permScore, 0.25)
                            yearMatched = True
                            break
                            
                # Base permutation score if year is missing or does not match
                if not yearMatched:
                    permScore = max(permScore, 0.10)
    
        if permNb >= MAX_PERMUTATIONS_PER_PENSIONER:
            break

    return permFound, permNb, permScore, collectedHits

def saveHitsToDatabase(uid, hits, score, maxAuthorityLinks=None):
    """Inserts Prosocour hits and their associated authority links into the opendata table."""
    # Prevent inserting empty results or completely unmatched records
    if not hits or score == 0.0:
        return
        
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        insertedAuthoritiesCount = 0
        
        for hit in hits:
            prosocourId = hit.get('id') or hit.get('source', {}).get('_id')
            if not prosocourId: 
                continue
                
            prosocourUrl = f"https://www.prosocour.chateauversailles-recherche.fr/info_personne/{prosocourId}"
            
            # Insert main Prosocour record. Ignores if already exists.
            cursor.execute("""
                INSERT INTO opendata (pensionnaire_uid, base, external_uid, url, score)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (pensionnaire_uid, base, external_uid) DO NOTHING
            """, (uid, 'prosocour', prosocourId, prosocourUrl, score))

            # Skip authority links processing if the threshold is already reached for this batch
            if maxAuthorityLinks is not None and insertedAuthoritiesCount >= maxAuthorityLinks:
                continue

            # Insert linked authority records
            source = hit.get('source', {})
            liensAutorite = source.get('liens_autorite', [])
            
            for lien in liensAutorite:
                baseName = lien.get('titre', 'unknown').lower()
                linkUrl = lien.get('url', '')
                if not baseName or not linkUrl:
                    continue
                
                # Extract the trailing identifier from the authority URL
                extUid = linkUrl.strip('/').split('/')[-1]
                
                # Insert the authority link, referencing the Prosocour ID as its parent for cascading updates
                cursor.execute("""
                    INSERT INTO opendata (pensionnaire_uid, base, external_uid, url, score, parent_external_uid)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (pensionnaire_uid, base, external_uid) DO NOTHING
                """, (uid, baseName, extUid, linkUrl, score, prosocourId))

                insertedAuthoritiesCount += 1
            
                # Halt authority link insertion immediately if the threshold is reached
                if maxAuthorityLinks is not None and insertedAuthoritiesCount >= maxAuthorityLinks:
                    break
            
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Database insertion error: {e}")

def main():
    # Init of Prosocour provider
    providerProsocour = Prosocour()
    
    print("Retrieving pensioners from database...")
    pensionnaires = fetchPensioner()
    totalCount = len(pensionnaires)

    # Initialize dictionary to track processing volume and score distribution per class
    classStats = {i: {'total': 0, 'found': 0, 'perfect': 0, 'good': 0, 'other': 0} for i in range(1, 8)}

    #Variable for percentage of pensioners found
    countPerfect = 0
    countGood = 0
    countOther = 0
    
    print(f"Processing {totalCount} records...\n")
    print("[Iteration] : [Class] : [First Name] [Last Name] : [Search details] : sco=[Final score]")
    print("  -> Details (Standard search)     : adv=[Nb advanced results] sim=[Nb simple results]")
    print("  -> Details (Permutation search)  : permFound=[Nb results] permNb=[Nb attempted queries]")
    print()
    
    iteration = 0
    foundCount = 0
    
    for p in pensionnaires:
        iteration += 1
        pClass = p['class']
        classStats[pClass]['total'] += 1    
        
        # Advanced Search
        time.sleep(TIME_BETWEEN_EACH_CALL)
        resultsAdv = providerProsocour.fetch(query=None, name=p['name'], surname=p['surname'])
        matchAdv = len(resultsAdv)
        
        # Simple Search
        time.sleep(TIME_BETWEEN_EACH_CALL)
        querySimple = f"{p['name']} {p['surname']}".strip()
        resultsSim = providerProsocour.fetch(query=querySimple)
        matchSim = len(resultsSim)
        
        # Scoring System:
        # 1.0 : Single advanced match confirmed by birth year (+/- 1 year).
        # 0.8 : Multiple advanced matches, but one is confirmed by birth year.
        # 0.7 : Single advanced match, but birth year is missing or doesn't match.
        # 0.6 : Simple match confirmed by birth year.
        # 0.5 : Multiple advanced matches, no birth year confirmation.
        # 0.3 : Simple match only, no birth year confirmation.
        # 0.0 : No matches found.

        #Permutation (for each case found)
        # 0.25: Permutation advanced match confirmed by birth year.
        # 0.10: Permutation advanced match, no birth year confirmation.
        
        score = 0.0
        dbYear = p['birth_year']
        yearMatched = False
        acceptableYears = []
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
            permFound, permNb, permScore, permHits = evaluatePermutations(providerProsocour, p['name'], p['surname'], acceptableYears)
            
            if permNb > 0:
                if permFound > 0:
                    foundCount += 1
                    classStats[pClass]['found'] += 1
                    saveHitsToDatabase(p['uid'], permHits, permScore, maxAuthorityLinks=MAX_AUTHORITY_LINKS_PER_PERMUTATION)

                    # Track global and class-specific score distribution for permutations
                    if permScore == 1.0:
                        countPerfect += 1
                        classStats[pClass]['perfect'] += 1
                    elif permScore >= 0.5:
                        countGood += 1
                        classStats[pClass]['good'] += 1
                    elif permScore > 0.0:
                        countOther += 1
                        classStats[pClass]['other'] += 1

                print(f"{iteration} : {pClass} : {p['name']} {p['surname']} : permFound={permFound} permNb={permNb} : sco={permScore}")
                continue # Skip the standard print format below

        if score > 0.0:
            foundCount += 1
            classStats[pClass]['found'] += 1
            allPrimaryHits = resultsAdv + resultsSim
            saveHitsToDatabase(p['uid'], allPrimaryHits, score)

            # Track global and class-specific score distribution for primary searches
            if score == 1.0:
                countPerfect += 1
                classStats[pClass]['perfect'] += 1
            elif score >= 0.5:
                countGood += 1
                classStats[pClass]['good'] += 1
            elif score > 0.0:
                countOther += 1
                classStats[pClass]['other'] += 1

        # Final Output Formatting
        print(f"{iteration} : {pClass} : {p['name']} {p['surname']} : adv={matchAdv} sim={matchSim} : sco={score}")

   # Final summary

    print("\n" + "="*40)
    print("Final summary and statistics\n")
    print(f"Total processed: {totalCount}")
    
    countNotFound = totalCount - foundCount

    if totalCount > 0:
        successRate = (foundCount / totalCount) * 100
        perfectRate = (countPerfect / totalCount) * 100
        goodRate = (countGood / totalCount) * 100
        otherRate = (countOther / totalCount) * 100
        notFoundRate = (countNotFound / totalCount) * 100
    else:
        successRate = perfectRate = goodRate = otherRate = notFoundRate = 0.0

    print(f"Overall Success rate: {successRate:.2f}% ({foundCount} records found)")
    print(f"  - Perfect matches (score 1.0): {perfectRate:.2f}% ({countPerfect})")
    print(f"  - Good matches (score 0.5 to <1.0): {goodRate:.2f}% ({countGood})")
    print(f"  - Other matches (score < 0.5): {otherRate:.2f}% ({countOther})")
    print(f"  - Not found (score 0.0): {notFoundRate:.2f}% ({countNotFound})\n")
    
    # Iterate through classes to output isolated success rates and score distributions
    for c in range(1, 8):
        cTotal = classStats[c]['total']
        cFound = classStats[c]['found']
        
        if cTotal > 0:
            cRate = (cFound / cTotal) * 100
            cPerfect = classStats[c]['perfect']
            cGood = classStats[c]['good']
            cOther = classStats[c]['other']
            cNotFound = cTotal - cFound
            
            print(f"Class {c}: {cRate:.2f}% success ({cFound}/{cTotal} found)")
            print(f"  - Perfect: {cPerfect} | Good: {cGood} | Other: {cOther} | Not Found: {cNotFound}")

if __name__ == "__main__":
    main()