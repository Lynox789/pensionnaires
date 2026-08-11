import psycopg2
import re
from urllib.parse import unquote
from config import DB_CONFIG

# Compile specific regex patterns to extract IDs precisely for each base
urlPatterns = {
    'gnd': re.compile(r'nid(?:=|%3D)(\d+)'),
    'isni': re.compile(r'ISN(?::|%3A)([0-9X]{16})'),
    'cths': re.compile(r'id=(\d+)'),
    'data bnf': re.compile(r'data\.bnf\.fr/(?:fr/)?(\d+)'),
    'viaf': re.compile(r'viaf\.org/viaf/(\d+)'),
    'an': re.compile(r'notProdId=([A-Z0-9_]+)', re.IGNORECASE),
    'archives nationales': re.compile(r'notProdId=([A-Z0-9_]+)', re.IGNORECASE),
    'idref': re.compile(r'idref\.fr/(\d+)'),
    'biblissima': re.compile(r'Item:(Q\d+)', re.IGNORECASE),
    'bne': re.compile(r'(?:resource/|authority_id=)([A-Z0-9]+)', re.IGNORECASE),
    'bsz': re.compile(r'TRM=gnd(?:%3A|:)(\d+)', re.IGNORECASE),
    'cinii': re.compile(r'author/([A-Z0-9]+)', re.IGNORECASE)
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