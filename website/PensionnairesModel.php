<?php
require_once 'Database.php';

class PensionnairesModel {
    private $pdo;

    public function __construct() {
        // Initialize database connection
        $db = new Database();
        $this->pdo = $db->getConnection();
    }

    //Retrieve global statistics (total count and formatted total amount)
    public function getStats($searchQuery = '', $deptFilter = '') {
        $sql = "SELECT COUNT(id) as total_count, COALESCE(SUM(total_amount), 0) as total_amount FROM pensionnaires WHERE 1=1";
        $params = [];

        $this->applyFilters($sql, $params, $searchQuery, $deptFilter);

        $stmt = $this->pdo->prepare($sql);
        $stmt->execute($params);
        $row = $stmt->fetch();

        // Format the total amount (e.g., 32000000 -> 32 M)
        $montantFormatte = "0";
        if ($row['total_amount'] > 1000000) {
            $montantFormatte = round($row['total_amount'] / 1000000, 1) . " M";
        } elseif ($row['total_amount'] > 0) {
            $montantFormatte = number_format($row['total_amount'], 0, ',', ' ');
        }

        return [
            'count' => $row['total_count'],
            'amount' => $montantFormatte
        ];
    }

    //Retrieve a paginated and sorted list of pensioners using simple search criteria
    public function search($searchQuery = '', $deptFilter = '', $sort = 'alpha', $limit = 50, $offset = 0) {
        $sql = "SELECT * FROM pensionnaires WHERE 1=1";
        $params = [];
        $this->applyFilters($sql, $params, $searchQuery, $deptFilter);
        
        // Apply sorting logic
        $orderSql = " ORDER BY last_name ASC, first_name ASC";
        if ($sort === 'amount_desc') {
            $orderSql = " ORDER BY total_amount DESC NULLS LAST, last_name ASC, first_name ASC";
        } elseif ($sort === 'amount_asc') {
            $orderSql = " ORDER BY total_amount ASC NULLS FIRST, last_name ASC, first_name ASC";
        }
        
        $sql .= $orderSql . " LIMIT :limit OFFSET :offset";
        $params[':limit'] = $limit;
        $params[':offset'] = $offset;

        $stmt = $this->pdo->prepare($sql);
        
        // Bind parameters with appropriate data types for limit and offset
        foreach ($params as $key => &$val) {
            if ($key === ':limit' || $key === ':offset') {
                $stmt->bindParam($key, $val, PDO::PARAM_INT);
            } else {
                $stmt->bindParam($key, $val, PDO::PARAM_STR);
            }
        }
        $stmt->execute();
        return $stmt->fetchAll();
    }

    //Fetch a single pensioner record by its primary key
    public function getPensionnaireById($id) {
        $sql = "SELECT * FROM pensionnaires WHERE id = :id";
        $stmt = $this->pdo->prepare($sql);
        $stmt->execute([':id' => $id]);
        return $stmt->fetch();
    }
    
    // Fetch related external OpenData links for a specific pensioner
    public function getOpendataLinks($uid) {
        $sql = "SELECT base, url FROM opendata WHERE pensionnaire_uid = :uid ORDER BY base ASC";
        $stmt = $this->pdo->prepare($sql);
        $stmt->execute([':uid' => $uid]);
        return $stmt->fetchAll();
    }


    //Helper method to append basic search filters to the SQL query
    private function applyFilters(&$sql, &$params, $searchQuery, $deptFilter) {
        if (!empty($searchQuery)) {
            // Search across names, jobs, and detailed pension JSON texts
            $sql .= " AND (last_name ILIKE :q OR first_name ILIKE :q OR jobs::text ILIKE :q OR detailed_pensions::text ILIKE :q)";
            $params[':q'] = "%" . $searchQuery . "%";
        }

        if (!empty($deptFilter)) {
            // Filter by department within the detailed_pensions JSON text
            $sql .= " AND detailed_pensions::text ILIKE :dept";
            $params[':dept'] = "%\"department\": \"%" . $deptFilter . "%\"%";
        }
    }

    //Retrieve the total count of results for an advanced search
    public function getAdvancedStats($criteria) {
        $sql = "SELECT COUNT(id) as total_count FROM pensionnaires WHERE 1=1";
        $params = [];
        $this->applyAdvancedFilters($sql, $params, $criteria);
        $stmt = $this->pdo->prepare($sql);
        $stmt->execute($params);
        return $stmt->fetch()['total_count'] ?? 0;
    }

    
    //Retrieve a paginated and sorted list of pensioners using advanced search criteria 
    public function advancedSearch($criteria, $sort = 'alpha', $limit = 50, $offset = 0) {
        $sql = "SELECT * FROM pensionnaires WHERE 1=1";
        $params = [];
        $this->applyAdvancedFilters($sql, $params, $criteria);
        
        // Apply sorting logic
        $orderSql = " ORDER BY last_name ASC, first_name ASC";
        if ($sort === 'amount_desc') {
            $orderSql = " ORDER BY total_amount DESC NULLS LAST, last_name ASC, first_name ASC";
        } elseif ($sort === 'amount_asc') {
            $orderSql = " ORDER BY total_amount ASC NULLS FIRST, last_name ASC, first_name ASC";
        }

        $sql .= $orderSql . " LIMIT :limit OFFSET :offset";
        $params[':limit'] = $limit;
        $params[':offset'] = $offset;

        $stmt = $this->pdo->prepare($sql);
        foreach ($params as $key => &$val) {
            if ($key === ':limit' || $key === ':offset') {
                $stmt->bindParam($key, $val, PDO::PARAM_INT);
            } else {
                $stmt->bindParam($key, $val, PDO::PARAM_STR);
            }
        }
        $stmt->execute();
        return $stmt->fetchAll();
    }

    //Helper method to append complex advanced search filters to the SQL query
    private function applyAdvancedFilters(&$sql, &$params, $criteria) {
        foreach ($criteria as $index => $c) {
            $field = $c['field'] ?? '';
            $val = trim($c['value'] ?? '');
            
            if (empty($val) || empty($field)) continue;

            // Handle exact matches enclosed in double quotes
            $isExact = false;
            if (preg_match('/^"(.*)"$/', $val, $matches)) {
                $val = $matches[1];
                $isExact = true;
            }

            $paramName = ":adv_" . $index;
            
            if ($field === 'department') {
                $sql .= " AND detailed_pensions::text ILIKE $paramName";
                $params[$paramName] = "%\"department\": \"%" . $val . "%\"%";
            } elseif ($field === 'class') {
                // Special handling: querying class 7 automatically includes class 8
                $classVal = (int)$val;
                if ($classVal === 7) {
                    $sql .= " AND class IN (7, 8)";
                } else {
                    $sql .= " AND class = " . $classVal;
                }
            } else {
                // Map form fields to database columns
                switch ($field) {
                    case 'last_name': $dbCol = "last_name"; break;
                    case 'first_name': $dbCol = "first_name"; break;
                    case 'sex': $dbCol = "sex"; break;
                    case 'birth_year': $dbCol = "birth_year::text"; break;
                    default: $dbCol = "last_name";
                }

                // Apply either exact match or partial match (ILIKE)
                if ($isExact) {
                    $sql .= " AND $dbCol ILIKE $paramName";
                    $params[$paramName] = $val;
                } else {
                    $sql .= " AND $dbCol ILIKE $paramName";
                    $params[$paramName] = "%" . $val . "%";
                }
            }
        }
    }
}