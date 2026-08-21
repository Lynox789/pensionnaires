<?php

class Database {
    private $pdo;

    public function __construct() {
        // Locate and load the .env configuration file
        $envFile = __DIR__ . '/.env';
        if (!file_exists($envFile)) {
            throw new Exception(".env file missing");
        }

        // Parse the .env file into an associative array
        $env = parse_ini_file($envFile);
        if (!$env) {
            throw new Exception("Read error of .env file");
        }

        // Retrieve database credentials with default fallback values
        $host = $env['DB_HOST'] ?? '';
        $port = $env['DB_PORT'] ?? '';
        $dbname = $env['DB_NAME'] ?? '';
        $user = $env['DB_USER'] ?? '';
        $pass = $env['DB_PASS'] ?? '';

        // Establish the PostgreSQL connection using PDO
        $dsn = "pgsql:host={$host};port={$port};dbname={$dbname}";
        
        try {
            $this->pdo = new PDO($dsn, $user, $pass, [
                PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
                PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC
            ]);
        } catch (PDOException $e) {
            // Terminate script execution if the connection fails
            die("Connexion error to database : " . $e->getMessage());
        }
    }

    //Retrieve the active PDO database connection instance
    public function getConnection() {
        return $this->pdo;
    }
}