import psycopg2
import time
import datetime
import sys
import re
import concurrent.futures
from extractingPensioner import Prosocour
from config import DB_CONFIG

TIME_BETWEEN_EACH_CALL = 0.1
MAX_AUTHORITY_LINKS_PER_PERMUTATION = 10
MAX_PERMUTATIONS_PER_PENSIONER = 12
NUMBER_OF_CLASS = 8

#Variable to clean first and lastname
WORDS_TO_ERASE = {"de", "du", "des", "la", "le", "les", "l", "d"}
TITLES_PATTERN = re.compile(
    r'\b(baronne|baron|comte|comtesse|cte|princesse|prince|dlle|demoiselle|dame|anonyme|filleul|veuve|duc|duchesse|marquis|marquise|maréchal|maréchale|chevalier|abbé|vicomte|vicomtesse|cardinal|évêque|eveque|archevêque|archeveque|prélat|prelat|monseigneur|madame|mademoiselle)\b', 
    re.IGNORECASE
)

#regex for extracting prefix and suffix
#prefix : "fr. ", "fr.", "de ", "d' ", "d'", "le ", "la ", "l' ", "l'"
#suffix : " de", " d'"
PREFIXES_PATTERN = re.compile(r'^(?:fr\.\s*|de\s+|d\'\s*|le\s+|la\s+|l\'\s*)+', re.IGNORECASE)
SUFFIXES_PATTERN = re.compile(r'(?:\s+de|\s+d\')+$', re.IGNORECASE)

#regex for extracting year
YEAR_PATTERN = re.compile(r'\d{4}')
SPLIT_PATTERN = re.compile(r'[-\s]+')

NUMBER_OF_PENSIONERS_PER_CYCLE = 20


def isolatePrimaryFirstName(first_name):
    """Isolates the first word if first name has more than 3 words."""
    words = first_name.split()
    if len(words) > 3:
        return words[0]
    return first_name

def cleanLastName(last_name):
    """Removes titles from last name but keeps particles."""
    if not last_name:
        return ""
    
    last_name = last_name.strip()
    last_name = TITLES_PATTERN.sub('', last_name).strip()
    
    # Clean extra spaces left by title removal
    return re.sub(r'\s+', ' ', last_name).strip()

def cleanFirstName(first_name):
    """Cleans titles, prefixes, suffixes, and isolates primary name using pre-compiled regex."""
    if not first_name:
        return ""
    
    first_name = TITLES_PATTERN.sub('', first_name).strip()
    first_name = PREFIXES_PATTERN.sub('', first_name)
    first_name = SUFFIXES_PATTERN.sub('', first_name)
    
    first_name = isolatePrimaryFirstName(first_name)
    return first_name.strip()

def extractBirthYearFromHit(hit):
    """Extracts the 4-digit birth year from the specific JSON path in Prosocour's response."""
    try:
        # Extracting the date from the return JSON file from Prosocour
        dateStr = hit.get("source", {}).get("naissance", {}).get("date", {}).get("date", "")
        
        if dateStr:
            #use of the regex pattern to extract the year
            match = YEAR_PATTERN.search(str(dateStr))
            if match:
                return int(match.group())
    except (AttributeError, TypeError):
        pass
    
    return None

def fetchPensioner():
    """Retrieve 20 pensioners for each class from 1 to 7, including birth year."""
    query = f"""
            SELECT 
        id, 
        class, 
        COALESCE(last_name, '') AS last_name, 
        COALESCE(first_name, '') AS first_name, 
        birth_year, 
        uid
    FROM pensionnaires
    WHERE class BETWEEN 1 AND {NUMBER_OF_CLASS}
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
                "surname": cleanLastName(row[2]),
                "name": cleanFirstName(row[3]),
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
    nameParts = [part for part in SPLIT_PATTERN.split(name) if part and part.lower() not in WORDS_TO_ERASE]
    surnameParts = [part for part in SPLIT_PATTERN.split(surname) if part and part.lower() not in WORDS_TO_ERASE]
    
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


def formatTime(seconds):
    # Format seconds into HH:MM:SS
    return str(datetime.timedelta(seconds=int(seconds)))


def processPensionerWorker(p):
    """Worker function mapped to each thread to execute the API calls safely."""
    # Create an independent provider instance per thread
    provider = Prosocour()
    
    time.sleep(TIME_BETWEEN_EACH_CALL)
    resultsAdv = provider.fetch(query=None, name=p['name'], surname=p['surname'])
    matchAdv = len(resultsAdv)
    
    time.sleep(TIME_BETWEEN_EACH_CALL)
    querySimple = f"{p['name']} {p['surname']}".strip()
    resultsSim = provider.fetch(query=querySimple)
    matchSim = len(resultsSim)
    
    score = 0.0
    dbYear = p['birth_year']
    yearMatched = False
    acceptableYears = []
    
    if dbYear is not None:
        try:
            baseYear = int(dbYear)
            acceptableYears = [baseYear - 1, baseYear, baseYear + 1]
            
            for hit in resultsAdv:
                hitYear = extractBirthYearFromHit(hit)
                if hitYear in acceptableYears:
                    score = 1.0 if matchAdv == 1 else 0.8
                    yearMatched = True
                    break 
                    
            if not yearMatched:
                for hit in resultsSim:
                    hitYear = extractBirthYearFromHit(hit)
                    if hitYear in acceptableYears:
                        score = 0.6
                        yearMatched = True
                        break
        except ValueError:
            pass 
            
    if not yearMatched:
        if matchAdv == 1:
            score = 0.9
        elif matchAdv > 1:
            score = 0.5 
        elif matchSim > 0:
            score = 0.3 

    permFound, permNb, permScore, permHits = 0, 0, 0.0, []
    if score == 0.0:
        permFound, permNb, permScore, permHits = evaluatePermutations(provider, p['name'], p['surname'], acceptableYears)

    # Return a compiled result package to the main thread
    return {
        'p': p,
        'matchAdv': matchAdv,
        'matchSim': matchSim,
        'score': score,
        'permFound': permFound,
        'permNb': permNb,
        'permScore': permScore,
        'permHits': permHits,
        'allPrimaryHits': resultsAdv + resultsSim if score > 0.0 else []
    }

def main():
    scriptStartTime = time.time()
    
    print("Retrieving pensioners from database...")
    pensionnaires = fetchPensioner()
    totalCount = len(pensionnaires)

    classStats = {i: {'total': 0, 'found': 0, 'perfect': 0, 'good': 0, 'other': 0} for i in range(1, NUMBER_OF_CLASS + 1)}

    countPerfect = 0
    countGood = 0
    countOther = 0

    # Slice the pensioner list into cycles
    cycles = [pensionnaires[i:i + NUMBER_OF_PENSIONERS_PER_CYCLE] for i in range(0, totalCount, NUMBER_OF_PENSIONERS_PER_CYCLE)]
        
    print(f"Processing {totalCount} records (Multithreading Pensioners per cycle : {NUMBER_OF_PENSIONERS_PER_CYCLE})\n")
    print("[Iteration] : [Class] : [First Name] [Last Name] : [Search details] : sco=[Final score]")
    print("  -> Details (Standard search)     : adv=[Nb advanced results] sim=[Nb simple results]")
    print("  -> Details (Permutation search)  : permFound=[Nb results] permNb=[Nb attempted queries]")
    print()
    
    iteration = 0
    foundCount = 0
    consoleWidth = 100

    # Use ThreadPoolExecutor for concurrency
    with concurrent.futures.ThreadPoolExecutor(max_workers=NUMBER_OF_PENSIONERS_PER_CYCLE) as executor:
        for cycle in cycles:
            # Map evaluates the cycle in parallel and waits for all of them to finish
            results = list(executor.map(processPensionerWorker, cycle))
            
            # Process the results sequentially to preserve order and DB integrity
            for res in results:
                iteration += 1
                p = res['p']
                pClass = p['class']
                classStats[pClass]['total'] += 1    
                
                score = res['score']
                permScore = res['permScore']
                
                if score == 0.0:
                    if res['permNb'] > 0 and res['permFound'] > 0:
                        foundCount += 1
                        classStats[pClass]['found'] += 1
                        saveHitsToDatabase(p['uid'], res['permHits'], permScore, maxAuthorityLinks=MAX_AUTHORITY_LINKS_PER_PERMUTATION)

                        if permScore == 1.0:
                            countPerfect += 1
                            classStats[pClass]['perfect'] += 1
                        elif permScore >= 0.5:
                            countGood += 1
                            classStats[pClass]['good'] += 1
                        elif permScore > 0.0:
                            countOther += 1
                            classStats[pClass]['other'] += 1

                    elapsedSoFar = time.time() - scriptStartTime
                    avgTimePerIter = elapsedSoFar / iteration
                    etaSeconds = avgTimePerIter * (totalCount - iteration)
                    etaStr = formatTime(etaSeconds)

                    outputStr = f"{iteration} : {pClass} : {p['name']} {p['surname']} : permFound={res['permFound']} permNb={res['permNb']} : sco={permScore}"
                    spacesNeeded = max(1, consoleWidth - len(outputStr) - len(f" | ETA: {etaStr}"))
                    print(f"{outputStr}{' ' * spacesNeeded}| ETA: {etaStr}")
                    
                else:
                    foundCount += 1
                    classStats[pClass]['found'] += 1
                    saveHitsToDatabase(p['uid'], res['allPrimaryHits'], score)

                    if score == 1.0:
                        countPerfect += 1
                        classStats[pClass]['perfect'] += 1
                    elif score >= 0.5:
                        countGood += 1
                        classStats[pClass]['good'] += 1
                    elif score > 0.0:
                        countOther += 1
                        classStats[pClass]['other'] += 1

                    elapsedSoFar = time.time() - scriptStartTime
                    avgTimePerIter = elapsedSoFar / iteration
                    etaSeconds = avgTimePerIter * (totalCount - iteration)
                    etaStr = formatTime(etaSeconds)

                    outputStr = f"{iteration} : {pClass} : {p['name']} {p['surname']} : adv={res['matchAdv']} sim={res['matchSim']} : sco={score}"
                    spacesNeeded = max(1, consoleWidth - len(outputStr) - len(f" | ETA: {etaStr}"))
                    print(f"{outputStr}{' ' * spacesNeeded}| ETA: {etaStr}")

    # Final summary
    totalTimeSeconds = time.time() - scriptStartTime
    avgTimePerCase = totalTimeSeconds / totalCount if totalCount > 0 else 0

    print("\n" + "="*40)
    print("Final summary and statistics\n")
    print(f"Total processed: {totalCount}")
    print(f"Total time elapsed: {formatTime(totalTimeSeconds)}")
    print(f"Average time per case: {avgTimePerCase:.2f} seconds\n")
    
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
    
    for c in range(1, NUMBER_OF_CLASS + 1):
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

    #save in file summary the results
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"summary_stats_{timestamp}.txt"
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n" + "="*40 + "\n")
            f.write("Final summary and statistics\n\n")
            f.write(f"Total processed: {totalCount}\n")
            f.write(f"Total time elapsed: {formatTime(totalTimeSeconds)}\n")
            f.write(f"Average time per case: {avgTimePerCase:.2f} seconds\n\n")
            f.write(f"Overall Success rate: {successRate:.2f}% ({foundCount} records found)\n")
            f.write(f"  - Perfect matches (score 1.0): {perfectRate:.2f}% ({countPerfect})\n")
            f.write(f"  - Good matches (score 0.5 to <1.0): {goodRate:.2f}% ({countGood})\n")
            f.write(f"  - Other matches (score < 0.5): {otherRate:.2f}% ({countOther})\n")
            f.write(f"  - Not found (score 0.0): {notFoundRate:.2f}% ({countNotFound})\n\n")
            
            for c in range(1, NUMBER_OF_CLASS + 1):
                cTotal = classStats[c]['total']
                cFound = classStats[c]['found']
                
                if cTotal > 0:
                    cRate = (cFound / cTotal) * 100
                    cPerfect = classStats[c]['perfect']
                    cGood = classStats[c]['good']
                    cOther = classStats[c]['other']
                    cNotFound = cTotal - cFound
                    
                    f.write(f"Class {c}: {cRate:.2f}% success ({cFound}/{cTotal} found)\n")
                    f.write(f"  - Perfect: {cPerfect} | Good: {cGood} | Other: {cOther} | Not Found: {cNotFound}\n")
                    
        print(f"\n Stats save in {filename}")
    except Exception as e:
        print(f"\nError : {e}")

if __name__ == "__main__":
    main()