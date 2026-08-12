import psycopg2
import re
from urllib.parse import unquote
from config import DB_CONFIG

# Compile specific regex patterns to extract IDs precisely for each base
urlPatterns = {
    # Extracts the numeric ID following 'nid=' or 'gnd/'
    'gnd': re.compile(r'(?:nid(?:=|%3D)|gnd/)(\d+)', re.IGNORECASE),
    # Extracts the 16-character ID following 'ISN:' or 'isni.org/isni/'
    'isni': re.compile(r'(?:ISN(?::|%3A)|isni\.org/isni/)([0-9X]{16})', re.IGNORECASE),
    # Extracts the numeric ID following 'id='
    'cths': re.compile(r'id=(\d+)'),
    # Extracts the numeric ID following 'data.bnf.fr/', ignoring the optional '/fr/'
    'data bnf': re.compile(r'data\.bnf\.fr/(?:fr/)?(\d+)'),
    # Extracts the numeric ID following 'viaf.org/viaf/'
    'viaf': re.compile(r'viaf\.org/viaf/(\d+)'),
    # Extracts the alphanumeric ID following 'notProdId='
    'an': re.compile(r'notProdId=([A-Z0-9_]+)', re.IGNORECASE),
    # Extracts the alphanumeric ID following 'notProdId='
    'archives nationales': re.compile(r'notProdId=([A-Z0-9_]+)', re.IGNORECASE),
    # Extracts the numeric ID following 'idref.fr/'
    'idref': re.compile(r'idref\.fr/(\d+)'),
    # Extracts the Q-number following 'Item:'
    'biblissima': re.compile(r'Item:(Q\d+)', re.IGNORECASE),
    # Extracts the alphanumeric ID following 'resource/' or 'authority_id='
    'bne': re.compile(r'(?:resource/|authority_id=)([A-Z0-9]+)', re.IGNORECASE),
    # Extracts the numeric ID following 'TRM=gnd:'
    'bsz': re.compile(r'TRM=gnd(?:%3A|:)(\d+)', re.IGNORECASE),
    # Extracts the alphanumeric ID following 'author/'
    'cinii': re.compile(r'author/([A-Z0-9]+)', re.IGNORECASE),
    # Extracts the ID string following 'page/' or 'resource/', ignoring trailing parameters
    'dbpedia': re.compile(r'dbpedia\.org/(?:page|resource)/([^#?]+)', re.IGNORECASE),
    # Extracts the numeric ID following 'subjectid='
    'getty ulan': re.compile(r'subjectid=(\d+)', re.IGNORECASE),
    # Extracts the ID string following 'nla.gov.au/', ignoring trailing parameters
    'nla': re.compile(r'nla\.gov\.au/([^#?]+)', re.IGNORECASE),
    # Extracts the numeric ID following 'request='
    'nlaif': re.compile(r'request=(\d+)', re.IGNORECASE),
    # Extracts the numeric ID following 'request='
    'nli': re.compile(r'request=(\d+)', re.IGNORECASE),
    # Extracts the numeric ID following 'request='
    'nliaf': re.compile(r'request=(\d+)', re.IGNORECASE),
    # Extracts the numeric ID following 'request='
    'nlinsaf': re.compile(r'request=(\d+)', re.IGNORECASE),
    # Extracts the ID string following 'aut/', ignoring trailing parameters
    'nukat': re.compile(r'aut/([^#?]+)', re.IGNORECASE),
    # Extracts the ID string following '10.1093/oi/', ignoring trailing parameters
    'oxford reference': re.compile(r'10\.1093/oi/([^#?]+)', re.IGNORECASE),
    # Extracts the numeric ID following 'num_dept='
    'sycomore': re.compile(r'num_dept=(\d+)', re.IGNORECASE),
    # Extracts the alphanumeric ID following 'udId='
    'transcription du testament de pierre fournier par t. boudignon': re.compile(r'udId=([a-z0-9-]+)', re.IGNORECASE),
    # Extracts the numeric ID following 'subjectid='
    'ulan': re.compile(r'subjectid=(\d+)', re.IGNORECASE),

    # New cases from unknown bases    
    # Extracts the alphanumeric ID following 'ark:/12148/'
    'catalogue bnf': re.compile(r'ark:/12148/([a-z0-9]+)', re.IGNORECASE),
    # Extracts the alphanumeric ID following 'nome/'
    'sbn': re.compile(r'nome/([A-Z0-9]+)', re.IGNORECASE),
    # Extracts the numeric ID following 'descriptor-details/'
    'dbn': re.compile(r'descriptor-details/(\d+)', re.IGNORECASE),
    # Extracts the alphanumeric ID following 'nkp.cz/'
    'nkp': re.compile(r'nkp\.cz/([a-z0-9]+)', re.IGNORECASE),
    # Extracts the ID string following 'identities/', ignoring trailing parameters
    'worldcat': re.compile(r'identities/([^#?]+)', re.IGNORECASE),
    # Extracts the Q-number following 'wiki/'
    'wikidata': re.compile(r'wiki/(Q\d+)', re.IGNORECASE)
}

def cleanExternalUid(baseName, currentUid, url):
    """Analyze the URL and return the cleaned external ID."""
    if not url:
        return currentUid
        
    baseName = baseName.lower().strip()
    
    # Extract ID using defined regex patterns
    if baseName in urlPatterns:
        match = urlPatterns[baseName].search(url)
        if match:
            return match.group(1)
            
    cleanUid = currentUid
    
    # Remove file extensions
    if cleanUid.endswith('.html'):
        cleanUid = cleanUid.replace('.html', '')
        
    # Remove web anchors for bases without specific regex
    if '#' in cleanUid:
        cleanUid = cleanUid.split('#')[0]
        
    return cleanUid

def main():
    print("Connecting to the database...")
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Retrieve all opendata entries
        cursor.execute("SELECT id, base, external_uid, url FROM opendata;")
        rows = cursor.fetchall()
        
        updatesToProcess = []
        
        print(f"Found {len(rows)} records. Starting cleanup...")
        
        for row in rows:
            recordId, baseName, currentUid, url = row
            
            # Decode the URL to handle URL-encoded characters
            decodedUrl = unquote(url)
            
            newUid = cleanExternalUid(baseName, currentUid, decodedUrl)
            
            # Add to updates list if the ID was modified
            if newUid != currentUid and newUid:
                updatesToProcess.append((newUid, recordId))
        
        # Execute batch update in the database
        if updatesToProcess:
            print(f"{len(updatesToProcess)} IDs to fix. Executing updates...")
            cursor.executemany(
                "UPDATE opendata SET external_uid = %s WHERE id = %s;",
                updatesToProcess
            )
            conn.commit()
            print("Cleanup completed successfully!")
        else:
            print("No fragmented IDs needed to be fixed.")
            
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error during cleanup: {e}")

if __name__ == "__main__":
    main()